/**
 * @file utils.cpp, part of the project OpenDTA under Apache License 2.0
 * @author jdlph (jdlph@hotmail.com) and xzhou99 (xzhou74@asu.edu)
 * @brief Implementations of utilities
 *
 * @copyright Copyright (c) 2023 - 2025 Peiheng Li, Ph.D. and Xuesong (Simon) Zhou, Ph.D.
 */

#ifdef _WIN32
#define YAML_CPP_STATIC_DEFINE
#endif

#include <handles.h>
#include <stdcsv.h>

#ifdef __cpp_lib_filesystem
#include <filesystem>
#else
#include <experimental/filesystem>
#endif

#include <fstream>
#include <iostream>
#include <iomanip>

#include <yaml-cpp/yaml.h>

using namespace transoms;
using namespace std::string_literals;

#ifdef __cpp_lib_filesystem
namespace fs = std::filesystem;
#else
namespace fs = std::experimental::filesystem;
#endif

/**
 * @brief a helper struct to store the positions of headers related to VDFPeriod in link.csv
 *
 * @details it is to facilitate the operation on VDFPeriod in read_links()
 *
 * @note short is sufficient enough as we would not have a csv file with more than
 * 32,767 fields for this application
 */
struct HeaderPos {
    HeaderPos() : alpha_pos {-1}, beta_pos {-1}, cap_pos {-1}, fftt_pos {-1}
    {
    }

    short alpha_pos;
    short beta_pos;
    short cap_pos;
    short fftt_pos;
};

void NetworkHandle::auto_setup()
{
    const auto at = new AgentType();
    const auto dp = new DemandPeriod{Demand{at}};

    this->ats.push_back(at);
    this->dps.push_back(dp);
}

void NetworkHandle::to_lower(std::string& str)
{
    std::transform(str.cbegin(), str.cend(), str.begin(),
                   [](unsigned char c) {return std::tolower(c);});
}

void NetworkHandle::update_ue_settings(bool load_columns,
                                       unsigned short column_gen_num,
                                       unsigned short column_opd_num)
{
    // perform sanity check first
    if (!load_columns && !column_gen_num)
    {
        std::cout << "WRONG SETTINGS FOUND FOR load_columns AND column_gen_num!\n";
        std::cout << "USE DEFAULT SETTINGS, load_columns: false, column_gen_num: 20, column_opd_num: 20\n";
        return;
    }

    this->m_uses_existing_cols = load_columns;
    this->column_gen_num = column_gen_num;
    this->column_opd_num = column_opd_num;
}

void NetworkHandle::update_simulation_settings(unsigned short res, const std::string& model)
{
    this->m_enable_simu = true;
    this->simu_res = res;

    if (model == "spatial_queue"s || model == "spatial queue"s)
        this->tfm = TrafficFlowModel::spatial_queue;
    else if (model == "kinematic_wave"s || model == "kinematic wave"s)
        this->tfm = TrafficFlowModel::kinematic_wave;

    // set up simulation duration
    auto st = this->dps.front()->get_start_time();
    auto et = this->dps.back()->get_end_time();

    this->simu_dur = et - st;
}

// V1-c: link_supply.csv - THE explicit mu(t) input (spec section 2).
// Absolute-clock windows (HHMM or HHMMSS, [start, end)), mu in veh/h,
// per_lane values scaled to all lanes here so the engine sees one basis.
void NetworkHandle::read_link_supply()
{
    auto path = (this->input_dir / "link_supply.csv").string();
    if (!fs::exists(path))
        return;

    auto parse_clock = [](const std::string& s) -> unsigned {
        if (s.size() != 4 && s.size() != 6)
            throw std::runtime_error{
                "link_supply.csv: window token '" + s + "' is not HHMM or HHMMSS"
            };

        auto h = std::stoul(s.substr(0, 2));
        auto m = std::stoul(s.substr(2, 2));
        auto sec = s.size() == 6 ? std::stoul(s.substr(4, 2)) : 0;
        return static_cast<unsigned>(h * 3600 + m * 60 + sec);
    };

    auto reader = miocsv::DictReader(path);
    for (const auto& line : reader)
    {
        std::string link_id = line["link_id"];
        const Link* link = nullptr;
        try
        {
            link = this->net.get_link(link_id);
        }
        catch (const std::exception& e)
        {
            throw std::runtime_error{
                "link_supply.csv references unknown link_id " + link_id
            };
        }

        auto beg = parse_clock(line["window_start"]);
        auto end = parse_clock(line["window_end"]);
        if (end <= beg)
            throw std::runtime_error{
                "link_supply.csv: empty or reversed window for link " + link_id
            };

        auto unit = line["mu_unit"];
        this->to_lower(unit);
        if (unit != "vph"s && unit != "veh/h"s)
            throw std::runtime_error{
                "BLOCKED-SUPPLY_UNIT_UNDEFINED: link " + link_id
                + " mu_unit '" + unit + "' (must be vph or veh/h)"
            };

        auto basis = line["per_lane_or_all_lanes"];
        this->to_lower(basis);
        if (basis != "per_lane"s && basis != "all_lanes"s)
            throw std::runtime_error{
                "BLOCKED-SUPPLY_UNIT_UNDEFINED: link " + link_id
                + " per_lane_or_all_lanes '" + basis + "'"
            };

        auto mu = std::stod(line["mu_value"]);
        if (mu < 0)
            throw std::runtime_error{
                "link_supply.csv: negative mu_value for link " + link_id
            };

        if (basis == "per_lane"s)
            mu *= link->get_lane_num();

        double lanes_open = link->get_lane_num();
        try
        {
            auto lo = std::stod(line["lanes_open"]);
            if (lo >= 0)
                lanes_open = lo;
        }
        catch (const std::exception& e)
        {
            // optional; only the mu dimension acts in v1 anyway
        }

        std::string source;
        try
        {
            source = line["source"];
        }
        catch (const std::exception& e)
        {
            // optional
        }

        this->link_supply[link->get_no()].push_back(
            {beg, end, mu, lanes_open, source});
    }

    // sort and reject overlaps per link
    for (auto& [no, wins] : this->link_supply)
    {
        std::sort(wins.begin(), wins.end(),
                  [](const SupplyWindow& a, const SupplyWindow& b) {
                      return a.beg_sec < b.beg_sec;
                  });
        for (std::vector<SupplyWindow>::size_type i = 1; i != wins.size(); ++i)
        {
            if (wins[i].beg_sec < wins[i - 1].end_sec)
                throw std::runtime_error{
                    "link_supply.csv: overlapping windows on link no "
                    + std::to_string(no)
                };
        }
    }

    std::cout << "link_supply.csv loaded: " << this->link_supply.size()
              << " link(s) with explicit mu(t)\n";
}

// V1-b: the nine READY statuses (OPENDTA_V1_MVP_SPEC.md section 1). Every
// run prints all nine before any computation; any BLOCKED aborts AFTER the
// full report so the user sees where they stand without reading configs.
void NetworkHandle::report_readiness()
{
    struct Status {
        const char* name;
        std::string level;
        std::string note;
    };

    const bool validation = this->run_mode == RunMode::validation;
    std::vector<Status> ss;
    std::vector<std::string> blocked;
    bool def_mu = false;
    bool def_profile = false;

    auto add = [&](const char* name, std::string level, std::string note) {
        if (level.rfind("BLOCKED", 0) == 0)
            blocked.push_back(level);

        ss.push_back({name, std::move(level), std::move(note)});
    };

    auto n_nodes = this->net.get_nodes().size();
    auto n_links = this->net.get_links().size();
    if (n_nodes && n_links)
        add("NETWORK_READY", "PASS",
            std::to_string(n_nodes) + " nodes, " + std::to_string(n_links) + " links");
    else
        add("NETWORK_READY", "BLOCKED-NETWORK_EMPTY", "no nodes or links loaded");

    // mu(t) is THE explicit primary supply input (spec section 2): links
    // covered by link_supply.csv use it; the rest fall back to the
    // capacity-derived constant - a disclosed default in smoke mode and a
    // blocker in validation mode
    auto n_supply = this->link_supply.size();
    auto n_default = n_links > n_supply ? n_links - n_supply : 0;
    if (n_supply && !n_default)
        add("SUPPLY_MU_READY", "PASS",
            std::to_string(n_supply) + " link(s) with explicit mu(t) from link_supply.csv");
    else if (validation)
        add("SUPPLY_MU_READY", "BLOCKED-MU_T_NOT_VALIDATED",
            n_supply ? std::to_string(n_default) + " link(s) without an explicit mu(t) source"
                     : "no SLC/explicit mu(t) source (link_supply.csv absent)");
    else
    {
        def_mu = true;
        add("SUPPLY_MU_READY", "PASS_WITH_DEFAULT",
            n_supply ? std::to_string(n_supply) + " link(s) explicit, "
                       + std::to_string(n_default) + " on capacity default"
                     : "constant mu from link capacity (period_capacity level)");
    }

    size_type n_cols = 0;
    double od_vol = 0;
    for (auto& cv : this->cp.get_column_vecs())
    {
        n_cols += cv.get_column_num();
        od_vol += cv.get_volume();
    }

    if (this->m_uses_existing_cols)
    {
        if (n_cols)
            add("PATH_COLUMN_READY", "PASS",
                std::to_string(n_cols) + " frozen columns (load_columns)");
        else
            add("PATH_COLUMN_READY", "BLOCKED-PATH_COLUMNS_EMPTY",
                "load_columns produced no columns");
    }
    else if (validation)
        add("PATH_COLUMN_READY", "BLOCKED-PATH_NOT_FROZEN",
            "columns would be generated in-run (find_ue); validation requires a frozen path set");
    else
        add("PATH_COLUMN_READY", "PASS_WITH_DEFAULT",
            "columns generated in-run by find_ue (not frozen)");

    if (od_vol > 0)
        add("PATH_FLOW_READY", "PASS",
            "total OD volume " + std::to_string(od_vol));
    else
        add("PATH_FLOW_READY", "BLOCKED-NO_DEMAND", "zero total demand");

    if (!this->dep_profiles.empty() && !this->profile_bindings.empty())
        add("DEPARTURE_PROFILE_READY", "PASS",
            std::to_string(this->dep_profiles.size()) + " profile(s) bound (F03c)");
    else if (validation)
        add("DEPARTURE_PROFILE_READY", "BLOCKED-PROFILE_SOURCE_MISSING",
            "no bound departure profile; validation requires a sourced profile");
    else
    {
        def_profile = true;
        add("DEPARTURE_PROFILE_READY", "PASS_WITH_DEFAULT",
            "uniform in-period departures (S2b)");
    }

    if (od_vol > 0 && !this->dps.empty())
        add("VEHICLE_GENERATION_READY", "PASS",
            "S2a largest-remainder over " + std::to_string(this->dps.size()) + " period(s)");
    else
        add("VEHICLE_GENERATION_READY", "BLOCKED-NO_DEMAND",
            "no demand periods or zero demand");

    if (this->m_enable_simu)
    {
        std::string model = this->uses_point_queue_model() ? "point_queue"
                          : this->uses_spatial_queue_model() ? "spatial_queue"
                          : "kinematic_wave";
        add("DNL_LOADING_READY", "PASS",
            model + " at " + std::to_string(this->simu_res) + " s");
    }
    else
        add("DNL_LOADING_READY", "WARN", "simulation disabled - UE only run");

    if (this->enables_output())
        add("RESULT_OUTPUT_READY", "PASS", "output enabled");
    else
        add("RESULT_OUTPUT_READY", "WARN", "outputs disabled");

    if (this->m_enable_simu && this->saves_trajectory()
        && this->saves_link_performance_dta())
        add("VISUALIZATION_READY", "PASS",
            "trajectories + TD link performance readable by GUI/NeXTA");
    else
        add("VISUALIZATION_READY", "WARN",
            "trajectory or TD link output disabled - GUI view unavailable");

    std::cout << "==== readiness (run_mode = "
              << (validation ? "validation" : "smoke") << ") ====\n";
    for (const auto& s : ss)
        std::cout << "  " << s.name << ": " << s.level << " -- " << s.note << '\n';

    // V1-d: retain the outcome so run_summary.json can echo all_gate_status
    // and the provenance stamps without recomputing (and possibly disagreeing)
    this->gate_status.clear();
    for (const auto& s : ss)
        this->gate_status.emplace_back(s.name, s.level);

    this->used_default_mu = def_mu;
    this->used_default_profile = def_profile;
    this->validation_eligible = validation && blocked.empty() && !def_mu && !def_profile;

    if (this->enables_output())
    {
        std::ofstream f((this->output_dir / "readiness_report.json").string());
        f << "{\n \"run_mode\": \"" << (validation ? "validation" : "smoke")
          << "\",\n \"used_default_mu\": " << (def_mu ? "true" : "false")
          << ",\n \"used_default_profile\": " << (def_profile ? "true" : "false")
          << ",\n \"links_from_supply\": " << n_supply
          << ",\n \"links_from_default\": " << n_default
          << ",\n \"validation_eligible\": "
          << (this->validation_eligible ? "true" : "false")
          << ",\n \"blocked\": [";
        for (std::vector<std::string>::size_type i = 0; i != blocked.size(); ++i)
            f << (i ? ", " : "") << '"' << blocked[i] << '"';

        f << "],\n \"statuses\": {";
        for (std::vector<Status>::size_type i = 0; i != ss.size(); ++i)
            f << (i ? ",\n  " : "\n  ") << '"' << ss[i].name << "\": {\"status\": \""
              << ss[i].level << "\", \"note\": \"" << ss[i].note << "\"}";

        f << "\n }\n}\n";
    }

    if (!blocked.empty())
    {
        std::string msg = "readiness BLOCKED:";
        for (const auto& b : blocked)
            msg += ' ' + b;

        throw std::runtime_error{msg};
    }
}

void NetworkHandle::validate_demand_periods()
{
    if (this->dps.size() <= 1)
        return;

    // first, sort DemandPeriod instances according to the start time
    std::sort(this->dps.begin(), this->dps.end(),
              [](const DemandPeriod* left, const DemandPeriod* right){
                  return left->get_start_time() < right->get_start_time();
              });

    // second, check if there is overlap between two consecutive DemandPeriod instances
    auto curr_dp = this->dps.front();
    for (auto i = 1; i != this->dps.size(); ++i)
    {
        auto next_dp = this->dps[i];
        if (curr_dp->get_end_time() > next_dp->get_start_time())
        {
            std::string msg = {"Overlapping found between DemandPeriod "s
                               + curr_dp->get_time_period()
                               + " and DemandPeriod "s
                               + next_dp->get_time_period()};

            throw std::runtime_error{msg};
        }

        curr_dp = next_dp;
    }
}

std::string NetworkHandle::get_link_path_str(const Column& c)
{
    std::string str;
    for (auto j = c.get_link_num() - 1; j != 0; --j)
    {
        const auto link = this->get_link(c.get_link_no(j));
        str += link->get_id();
        str += ';';
    }

    const auto link = this->get_link(c.get_link_no(0));
    str += link->get_id();

    // it will be moved
    return str;
}

std::string NetworkHandle::get_node_path_str(const Column& c)
{
    std::string str;
    for (int j = c.get_link_num() - 1; j >= 0; --j)
    {
        const auto link = this->get_link(c.get_link_no(j));
        str += this->get_head_node_id(link);
        str += ';';
    }

    const auto link = this->get_link(c.get_link_no(0));
    str += this->get_tail_node_id(link);

    // it will be moved
    return str;
}

std::string NetworkHandle::get_node_path_coordinates(const Column& c)
{
    std::string str {"\"LINESTRING ("};
    for (int j = c.get_link_num() - 1; j >= 0; --j)
    {
        auto node_no = this->get_link(c.get_link_no(j))->get_head_node_no();
        const auto node = this->get_node(node_no);
        str += node->get_coordinate_str();
        str += ';';
    }

    auto node_no = this->get_link(c.get_link_no(0))->get_tail_node_no();
    const auto node = this->get_node(node_no);
    str += node->get_coordinate_str();
    str += ")\"";

    // it will be moved
    return str;
}

double NetworkHandle::cast_interval_to_minute_double(size_type i) const
{
    return static_cast<double>(i) * this->simu_res / SECONDS_IN_MINUTE;
}

std::string NetworkHandle::get_time_stamp(double t)
{
    static constexpr char sep = ':';

    unsigned short ti = std::floor(t);
    unsigned short hh = ti / MINUTES_IN_HOUR;
    unsigned short mm = ti % MINUTES_IN_HOUR;
    unsigned short ss = (t - ti) * SECONDS_IN_MINUTE;

    // convert time to hh::mm::ss format without leading 0 for hh
    // (e.g., 7AM will be displayed as 7:00:00 rather than 07:00:00)
    std::ostringstream os;
    os << hh << sep
       << std::setfill('0') << std::setw(2) << mm << sep << std::setw(2) << ss;

    return os.str();
}

void NetworkHandle::update_od_vol()
{
    for (auto& cv : this->cp.get_column_vecs())
    {
        auto vol = cv.get_volume();
        // col is const even without const identifier as a result of the underlying hashtable
        for (auto& col : cv.get_columns())
            const_cast<Column&>(col).set_od_vol(vol);
    }
}

void NetworkHandle::load_columns()
{
    auto reader = miocsv::DictReader(input_dir.string() + '/' + this->m_cols_filename);
    std::cout << "start loading columns from " << this->m_cols_filename << '\n';

    size_type count = 0;
    for (const auto& line : reader)
    {
        std::string oz_id;
        try
        {
            oz_id = line["o_zone_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "o_zone_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        std::string dz_id;
        try
        {
            dz_id = line["d_zone_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "d_zone_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        unsigned short oz_no;
        unsigned short dz_no;
        try
        {
            oz_no = this->net.get_zone_no(oz_id);
            dz_no = this->net.get_zone_no(dz_id);
        }
        catch(const std::exception& e)
        {
            continue;
        }

        std::string link_seq;
        try
        {
            link_seq = line["link_sequence"];
        }
        catch(std::exception& e)
        {
            // headers have no "link_sequence"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        if (link_seq.empty())
            continue;

        std::string at_str;
        try
        {
            at_str = line["agent_type"];
        }
        catch(const std::exception& e)
        {
            // headers have no "agent_type"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        if (at_str.empty())
            continue;

        const AgentType* at = nullptr;
        try
        {
            at = this->get_agent_type(at_str);
        }
        catch(const std::exception& e)
        {
            try
            {
                // add compatiblity for Path4GMNS and DTALite
                if (at_str.front() == 'a' || at_str.front() == 'p')
                    at = this->get_agent_type("auto");
                else
                {
                    std::cerr << "agent_type " << at_str
                              << "is not existing in settings.yml."
                              << "this record is discarded!\n";

                    continue;
                }
            }
            catch(const std::exception& e)
            {
                std::cerr << "default agent type auto is not existing\n";
                std::terminate();
            }
        }

        std::string dp_str;
        try
        {
            dp_str = line["demand_period"];
        }
        catch(const std::exception& e)
        {
            // headers have no "demand_period"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        if (dp_str.empty())
            continue;

        const DemandPeriod* dp = nullptr;
        try
        {
            dp = this->get_demand_period(dp_str);
        }
        catch(const std::exception& e)
        {
            std::cerr << "demand period " << dp_str
                      << "is not existing in settings.yml."
                      << "this record is discarded!\n";

            continue;
        }

        double vol;
        try
        {
            vol = std::stod(line["volume"]);
        }
        catch(const miocsv::NoRecord& nr)
        {
            // headers have no "demand_period"
            std::cerr << nr.what() << '\n';
            std::terminate();
        }
        catch(const std::exception& e)
        {
            // e could be either std::invalid_argument or std::out_of_range
            // skip this invalid record as we do require a valid volume
            std::cerr << e.what() << '\n';
            continue;
        }

        double toll = 0;
        try
        {
            toll = std::stod(line["toll"]);
        }
        catch(const std::exception& e)
        {
            // do nothing as toll is not critical
        }

        double dist;
        try
        {
            dist = std::stod(line["distance"]);
        }
        catch(const miocsv::NoRecord& nr)
        {
            // headers have no "distance"
            std::cerr << nr.what() << '\n';
            std::terminate();
        }
        catch(const std::exception& e)
        {
            // e could be either std::invalid_argument or std::out_of_range
            // skip this invalid record as we do require a valid distance
            continue;
        }

        std::string geo;
        try
        {
            geo = line["geometry"];
        }
        catch(const std::exception& e)
        {
            // do nothing as geo info is not critical
        }

        ColumnVecKey cvk {oz_no, dz_no, dp->get_no(), at->get_no()};
        this->cp.update(cvk, vol);

        const auto link_ids = miocsv::split(link_seq, ';');
        /**
         * 1. in case the input file is generated by DTALite which has trailing ';'.
         * 2. use int intentionally. otherwise, num will be an unsigned type which will
         * lead to problem in the link_path setup below (i will be inferred as an
         * unsigned type too).
         */
        const int num = link_ids.back() == "" ? link_ids.size() - 1: link_ids.size();

        // set up link_path
        std::vector<size_type> link_path;
        link_path.reserve(num);
        // link_path shall be in the reverse order for internal computation
        for (auto i = num - 1; i >= 0; --i)
            link_path.push_back(this->get_link(link_ids[i])->get_no());

        // create column and update column vector
        auto& cv = this->cp.get_column_vec(cvk);
        cv.update(Column{cv.get_column_num(), vol, dist, link_path, geo});

        if (count % 5000 == 0)
            std::cout << "loading columns: " << count << '\n';

        ++count;
    }

    // update OD Volume for each column
    this->update_od_vol();

    // update link properties
    this->update_link_and_column_volume(1, false);
    this->update_link_travel_time();

    std::cout << "loading columns completed. " << count << " columns are loaded.\n";
}

void NetworkHandle::read_demand(const std::string& file_path, unsigned short dp_no, unsigned short at_no)
{
    auto reader = miocsv::DictReader(file_path);

    size_type void_od_num = 0;
    double void_vol = 0;
    double total_vol = 0;
    for (const auto& line : reader)
    {
        double vol = 0;
        try
        {
            vol = std::stod(line["volume"]);
        }
        catch(const miocsv::NoRecord& nr)
        {
            // headers have no "volume"
            std::cerr << nr.what() << '\n';
            std::terminate();
        }
        catch(const std::exception& e)
        {
            continue;
        }

        if (vol <= 0)
        {
            ++void_od_num;
            continue;
        }

        std::string oz_id;
        try
        {
            oz_id = line["o_zone_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "o_zone_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        std::string dz_id;
        try
        {
            dz_id = line["d_zone_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "d_zone_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        if (oz_id == dz_id)
        {
            ++void_od_num;
            void_vol += vol;
            continue;
        }

        unsigned short oz_no;
        unsigned short dz_no;
        try
        {
            oz_no = this->net.get_zone_no(oz_id);
            dz_no = this->net.get_zone_no(dz_id);
        }
        catch(const std::exception& e)
        {
            continue;
        }

        this->cp.update(ColumnVecKey{oz_no, dz_no, dp_no, at_no}, vol);
        total_vol += vol;
    }

    // F03c: loaded volume per DemandPeriod for the G5 time contract audit
    this->demand_totals[dp_no] += total_vol;

    std::cout << "the total demand is " << total_vol << '\n'
              << void_od_num << " invalid OD pairs are discarded with a total volume of "
              << void_vol << '\n';
}

void NetworkHandle::read_demands()
{
    for (const auto& dp : this->dps)
    {
        // F03c: inactive registry rows load no demand
        if (!dp->is_active())
        {
            std::cout << "demand period " << dp->get_period()
                      << " is inactive; its demand is not loaded\n";
            continue;
        }

        auto dp_no = dp->get_no();
        for (auto& d : dp->get_demands())
        {
            auto at_no = d.get_agent_type_no();
            auto file_path = input_dir.string() + '/' + d.get_file_name();
            this->read_demand(file_path, dp_no, at_no);
        }

        // set up capacity ratio of affected links from special event
        const auto& se = dp->get_special_event();
        if (!se)
            continue;

        for (const auto& [link_id, r] : se->get_capacity_ratios())
        {
            // to do: wrap them into a single function?
            try
            {
                auto link = this->get_link(link_id);
                link->set_cap_ratio(dp_no, r);
            }
            catch (std::out_of_range& re)
            {
                continue;
            }
        }
    }
}

// parse HH:MM[:SS] into minutes; HH may exceed 24 on the monotone clock
// (e.g., 25:30:00 denotes 1:30 AM of the next day)
static double clock_str_to_minutes(const std::string& t)
{
    auto invalid = [&t]() {
        return std::invalid_argument{
            "invalid departure_time '" + t + "': expected HH:MM[:SS]"
        };
    };

    auto p1 = t.find(':');
    if (p1 == std::string::npos)
        throw invalid();

    auto p2 = t.find(':', p1 + 1);
    auto mm_str = p2 == std::string::npos ? t.substr(p1 + 1) : t.substr(p1 + 1, p2 - p1 - 1);
    auto ss_str = p2 == std::string::npos ? "0"s : t.substr(p2 + 1);

    try
    {
        std::size_t pos = 0;
        auto hh = std::stoi(t.substr(0, p1), &pos);
        if (pos != p1)
            throw invalid();

        auto mm = std::stoi(mm_str, &pos);
        if (pos != mm_str.size() || mm < 0 || mm >= 60)
            throw invalid();

        auto ss = std::stoi(ss_str, &pos);
        if (pos != ss_str.size() || ss < 0 || ss >= 60)
            throw invalid();

        return hh * 60.0 + mm + ss / 60.0;
    }
    catch (const std::invalid_argument&)
    {
        throw invalid();
    }
}

// canonical form is the integer period_id from F02; a leading 'P' (as in the
// gold dataset CSVs, e.g. P1) is accepted and stripped
static int parse_period_id_str(const std::string& s)
{
    auto t = (!s.empty() && (s.front() == 'P' || s.front() == 'p')) ? s.substr(1) : s;

    try
    {
        std::size_t pos = 0;
        auto id = std::stoi(t, &pos);
        if (pos != t.size())
            throw std::invalid_argument{""};

        return id;
    }
    catch (const std::exception&)
    {
        throw std::invalid_argument{
            "invalid period_id '" + s + "' in departure profile file: expected an integer or P<integer>"
        };
    }
}

// minutes on the folded 24h clock to HH:MM
static std::string format_clock(double minutes)
{
    auto m = static_cast<int>(minutes + 0.5);
    char buf[8];
    std::snprintf(buf, sizeof(buf), "%02d:%02d", m / 60, m % 60);
    return buf;
}

void NetworkHandle::read_departure_profiles()
{
    if (this->profile_bindings.empty())
        return;

    auto file_path = this->input_dir.string() + '/' + this->m_dep_profile_filename;
    if (!fs::exists(file_path))
        throw std::invalid_argument{
            "settings.yml declares departure_profile_binding but " + file_path + " is missing"
        };

    // 24h library keyed by profile_id only; a period_id column, if present,
    // is ignored (transitional files keep parsing)
    std::map<std::string, std::vector<DepartureProfile::Bin>> lib;
    bool checked_period_id_col = false;
    auto reader = miocsv::DictReader(file_path);
    for (const auto& line : reader)
    {
        std::string pid, dep_t, width_str, weight_str;
        try
        {
            pid = line["profile_id"];
            dep_t = line["departure_time"];
            width_str = line["bin_width_sec"];
            weight_str = line["weight"];
        }
        catch (const miocsv::NoRecord& nr)
        {
            throw std::invalid_argument{
                "departure profile file misses a required column: "s + nr.what()
            };
        }

        if (!checked_period_id_col)
        {
            checked_period_id_col = true;
            try
            {
                line["period_id"];
                std::cout << "note: the period_id column in " << this->m_dep_profile_filename
                          << " is ignored; profiles are full-day and periods bind via "
                          << "departure_profile_binding\n";
            }
            catch (const std::exception&)
            {
                // no such column: the canonical form
            }
        }

        auto start_min = clock_str_to_minutes(dep_t);
        auto width_min = std::stod(width_str) / 60;
        auto weight = std::stod(weight_str);
        if (width_min <= 0)
            throw std::invalid_argument{
                "nonpositive bin_width_sec for profile " + pid + " at " + dep_t
            };

        if (weight < 0)
            throw std::invalid_argument{
                "negative weight for profile " + pid + " at " + dep_t
            };

        lib[pid].push_back({start_min, width_min, weight});
    }

    // profiles actually referenced by bindings
    std::vector<std::string> referenced;
    for (const auto& b : this->profile_bindings)
    {
        bool seen = false;
        for (const auto& r : referenced)
        {
            if (r == b.profile_id)
            {
                seen = true;
                break;
            }
        }

        if (!seen)
            referenced.push_back(b.profile_id);
    }

    // the three-tier tolerance applies to the FULL-DAY sum only; the
    // conditional distributions below are invariant to this scaling
    for (const auto& name : referenced)
    {
        auto it = lib.find(name);
        if (it == lib.end())
            throw std::invalid_argument{
                "departure_profile_binding references profile " + name
                + " which is not present in " + this->m_dep_profile_filename
            };

        double total = 0;
        for (const auto& b : it->second)
            total += b.weight;

        auto gap = total > 1 ? total - 1 : 1 - total;
        if (gap > 0.02)
            throw std::invalid_argument{
                "profile " + name + " full-day weights sum to " + std::to_string(total)
                + "; |sum - 1| exceeds the 2e-2 repair tolerance"
            };

        if (gap > 1e-4)
            std::cerr << "profile " << name << " full-day weights sum to " << total
                      << "; normalized with recorded factor " << 1 / total << '\n';
    }

    // registry: unique period ids in settings order
    std::vector<const DemandPeriod*> registry;
    for (const auto dp : this->dps)
    {
        bool seen = false;
        for (const auto p : registry)
        {
            if (p->get_period_id() == dp->get_period_id())
            {
                seen = true;
                break;
            }
        }

        if (!seen)
            registry.push_back(dp);
    }

    // ---- G5 TIME CONTRACT AUDIT (format frozen by F03b review) ----
    std::cout << "==== G5 TIME CONTRACT AUDIT ====\n" << std::fixed << std::setprecision(6);
    for (const auto& name : referenced)
    {
        double total = 0;
        double covered = 0;
        for (const auto& b : lib[name])
        {
            total += b.weight;
            auto folded = b.start_min >= 1440 ? b.start_min - 1440 : b.start_min;
            for (const auto p : registry)
            {
                if (folded >= p->get_start_time() && folded < p->get_end_time())
                {
                    covered += b.weight;
                    break;
                }
            }
        }

        std::cout << "profile " << name << "  full-day sum = " << total
                  << "  uncovered mass (outside all periods) = " << total - covered << '\n';
    }

    static constexpr double s_r_floor = 1e-3;
    for (const auto p : registry)
    {
        std::cout << "Period: P" << p->get_period_id() << " / " << p->get_period()
                  << "   Window: " << format_clock(p->get_start_time()) << '-'
                  << format_clock(p->get_end_time())
                  << "   active: " << (p->is_active() ? "yes" : "no") << '\n';

        for (const auto& b : this->profile_bindings)
        {
            if (b.period_id != p->get_period_id())
                continue;

            std::cout << "  Agent: " << (b.agent_type.empty() ? "(all)"s : b.agent_type)
                      << "  Profile: " << b.profile_id << '\n';

            // clip the 24h profile to the half-open window by folded bin start
            std::vector<DepartureProfile::Bin> cond;
            double s_r = 0;
            for (const auto& bin : lib[b.profile_id])
            {
                auto folded = bin.start_min >= 1440 ? bin.start_min - 1440 : bin.start_min;
                if (folded >= p->get_start_time() && folded < p->get_end_time())
                {
                    cond.push_back({folded, bin.width_min, bin.weight});
                    s_r += bin.weight;
                }
            }

            std::cout << "    Raw profile mass in window   S_r = " << s_r << '\n';
            if (s_r < s_r_floor)
                throw std::invalid_argument{
                    "profile " + b.profile_id + " has essentially no mass ("
                    + std::to_string(s_r) + " < 1e-3) inside demand period "
                    + p->get_period() + "; refusing to renormalize noise"
                };

            std::sort(cond.begin(), cond.end(),
                      [](const DepartureProfile::Bin& l, const DepartureProfile::Bin& r) {
                          return l.start_min < r.start_min;
                      });

            double cond_sum = 0;
            for (auto& bin : cond)
            {
                bin.weight /= s_r;
                cond_sum += bin.weight;
            }

            // loaded demand for this (period, agent) across its DemandPeriod rows
            double demand = 0;
            bool loaded = false;
            for (const auto dp : this->dps)
            {
                if (dp->get_period_id() != p->get_period_id())
                    continue;

                if (!b.agent_type.empty()
                    && dp->get_demands().front().get_agent_type_name() != b.agent_type)
                    continue;

                auto it = this->demand_totals.find(dp->get_no());
                if (it != this->demand_totals.end())
                {
                    demand += it->second;
                    loaded = true;
                }
            }

            std::cout << "    Conditional weight sum           = " << cond_sum << '\n';
            if (loaded)
                std::cout << "    Period demand                    = " << demand << '\n'
                          << "    Allocated demand                 = " << demand * cond_sum << '\n';
            else
                std::cout << "    Period demand                    = n/a (not loaded)\n";

            std::cout << "    Earliest departure bin           = "
                      << format_clock(cond.front().start_min) << '\n'
                      << "    Latest departure bin start       = "
                      << format_clock(cond.back().start_min)
                      << "  (< " << format_clock(p->get_end_time()) << ": "
                      << (cond.back().start_min < p->get_end_time() ? "yes" : "NO - VIOLATION")
                      << ")\n";

            this->dep_profiles.push_back(
                new DepartureProfile{b.profile_id, b.period_id, b.agent_type, std::move(cond), s_r}
            );
        }
    }

    std::cout << this->dep_profiles.size()
              << " conditional departure distributions are loaded and validated\n";
    std::cout.unsetf(std::ios_base::fixed);
    std::cout << std::setprecision(6);
}

void NetworkHandle::read_nodes()
{
    auto reader = miocsv::DictReader(this->input_dir.string() + '/' + this->m_node_filename);

    size_type node_no = 0;
    for (const auto& line : reader)
    {
        std::string node_id;
        try
        {
            node_id = line["node_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "node_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        std::string zone_id;
        try
        {
            zone_id = line["zone_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "zone_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        double cx = COORD_X;
        double cy = COORD_Y;
        try
        {
            cx = std::stod(line["x_coord"]);
            cy = std::stod(line["y_coord"]);
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        bool activity_node = false;
        try
        {
            if (std::stoi(line["is_boundary"]))
                activity_node = true;
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        this->net.add_node(new Node{node_no, node_id, cx, cy, activity_node});

        unsigned short bin_index = 0;
        try
        {
            bin_index = std::stoi(line["bin_index"]);
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        // skip zone with empty id
        if (!zone_id.empty())
        {
            if (!this->has_zone_id(zone_id))
            {
                unsigned short no = this->get_zone_num();
                this->net.add_zone(new Zone{no, zone_id, bin_index});
            }

            this->get_zone(zone_id)->add_node(node_no);
            if (activity_node)
                this->get_zone(zone_id)->add_activity_node(node_no);
        }

        ++node_no;
    }

    std::cout << "the number of nodes is " << node_no << '\n'
              << "the number of zones is " << this->get_zone_num() << '\n';

}

void NetworkHandle::read_links()
{
    auto reader = miocsv::DictReader(this->input_dir.string() + '/' + this->m_link_filename);
    const auto& headers = reader.get_fieldnames();

    std::vector<HeaderPos> vec;
    for (unsigned short i = 0; i != this->dps.size();)
    {
        auto dp_id = std::to_string(++i);

        auto header_vdf_alpha {"VDF_alpha" + dp_id};
        auto header_vdf_beta {"VDF_beta" + dp_id};
        auto header_vdf_cap {"VDF_cap" + dp_id};
        auto header_vdf_fftt {"VDF_fftt" + dp_id};

        HeaderPos hp;

        try
        {
            hp.alpha_pos = headers.at(header_vdf_alpha);
        }
        catch(const std::out_of_range& re)
        {
            // do nothing
        }

        try
        {
            hp.beta_pos = headers.at(header_vdf_beta);
        }
        catch(const std::out_of_range& re)
        {
            // do nothing
        }

        try
        {
            hp.cap_pos = headers.at(header_vdf_cap);
        }
        catch(const std::out_of_range& re)
        {
            // do nothing
        }

        try
        {
            hp.fftt_pos = headers.at(header_vdf_fftt);
        }
        catch(const std::out_of_range& re)
        {
            // do nothing
        }

        vec.emplace_back(hp);
    }

    size_type link_no = 0;
    for (const auto& line : reader)
    {
        std::string link_id;
        try
        {
            link_id = line["link_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "link_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        std::string head_node_id;
        try
        {
            head_node_id = line["from_node_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "from_node_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        std::string tail_node_id;
        try
        {
            tail_node_id = line["to_node_id"];
        }
        catch(const std::exception& e)
        {
            // headers have no "to_node_id"
            std::cerr << e.what() << '\n';
            std::terminate();
        }

        size_type head_node_no, tail_node_no;
        try
        {
            head_node_no = this->net.get_node_no(head_node_id);
            tail_node_no = this->net.get_node_no(tail_node_id);
        }
        catch(const std::exception& e)
        {
            continue;
        }

        double len;
        try
        {
            len = std::stod(line["length"]) / this->len_unit_conversion_factor;
            if (len < 0)
            {
                std::cout << "Negative Length for Link " << link_id << ". Record Discarded.\n";
                continue;
            }
            else if (len == 0)
            {
                // std::cout << "Zero Length for Link " << link_id << ". Setting to Minimum Length.\n";
                // set a minimum length as it is a potential connector
                len = MIN_LINK_LENGTH;
            }
        }
        catch(const miocsv::NoRecord& nr)
        {
            // headers have no "length"
            std::cerr << nr.what() << '\n';
            std::terminate();
        }
        catch(const std::exception& e)
        {
            continue;
        }

        uint8_t lane_num = 1;
        try
        {
            lane_num = std::stoi(line["lanes"]);
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        // unsigned short lane_type = 1;
        // try
        // {
        //     lane_type = std::stoi(line["link_type"]);
        // }
        // catch(const std::exception& e)
        // {
        //     // do nothing
        // }

        double ffs = 60;
        try
        {
            ffs = std::stoi(line["free_speed"]);
        }
        catch(const std::exception& e)
        {
            // do nothing
        }
        // unit conversion
        ffs /= this->spd_unit_conversion_factor;

        double cap = 1999;
        try
        {
            cap = std::stoi(line["capacity"]);
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        double toll = 0;
        try
        {
            toll = std::stoi(line["toll"]);
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        std::string modes;
        try
        {
            line["allowed_uses"].empty() ? modes = ALL_MODES : modes = line["allowed_uses"];
        }
        catch(const std::exception& e)
        {
            modes = ALL_MODES;
        }

        std::string geo;
        try
        {
            geo = line["geometry"];
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        // F05-pre (M-13): optional per-link FD parameters; absent or
        // non-positive values fall back to the former global defaults
        double jam_density = JAM_DENSITY;
        try
        {
            auto v = std::stod(line["jam_density"]);
            if (v > 0)
                jam_density = v;
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        double backwave_speed = BACKWAVE_SPEED;
        try
        {
            auto v = std::stod(line["backwave_speed"]);
            if (v > 0)
                backwave_speed = v / this->spd_unit_conversion_factor;
        }
        catch(const std::exception& e)
        {
            // do nothing
        }

        auto link = new Link {
            link_id, link_no, head_node_no, tail_node_no,
            lane_num, cap, ffs, len, toll, modes, geo,
            jam_density, backwave_speed
        };

        uint8_t dp_no = 0;
        for (const auto& hp : vec)
        {
            double vdf_alpha = 0.15;
            try
            {
                vdf_alpha = std::stod(line[hp.alpha_pos]);
            }
            catch(const std::exception& e)
            {
                // do nothing
            }

            double vdf_beta = 4;
            try
            {
                vdf_beta = std::stod(line[hp.beta_pos]);
            }
            catch(const std::exception& e)
            {
                // do nothing
            }

            double vdf_cap = link->get_cap();
            try
            {
                vdf_cap = std::stod(line[hp.cap_pos]);
            }
            catch(const std::exception& e)
            {
                // do nothing
            }

            double vdf_fftt = link->get_fftt();
            try
            {
                vdf_fftt = std::stod(line[hp.fftt_pos]);
            }
            catch(const std::exception& e)
            {
                // do nothing
            }

            link->add_vdfperiod(VDFPeriod{dp_no++, vdf_alpha, vdf_beta, vdf_cap, vdf_fftt});
        }

        this->net.add_link(link);
        ++link_no;
    }

    std::cout << "the number of links is " << link_no << '\n';
}

void NetworkHandle::read_network()
{
    read_nodes();
    read_links();
}

void NetworkHandle::read_settings_yml(const std::string& file_path)
{
    YAML::Node settings = YAML::LoadFile(file_path);

    // set up network units
    try
    {
        const YAML::Node& network = settings["network"];

        try
        {
            auto length_unit = network["length_unit"].as<std::string>();
            this->to_lower(length_unit);

            if (length_unit == "meter"s || length_unit == "meters"s || length_unit == "m"s)
                this->len_unit_conversion_factor = MILE_TO_METER;
            else if (length_unit == "kilometer"s || length_unit == "kilometers"s || length_unit == "km"s)
                this->len_unit_conversion_factor = MPH_TO_KMPH;
            else if (length_unit == "mile"s || length_unit == "miles"s || length_unit == "mi"s)
                this->len_unit_conversion_factor = 1.0;
            else
            {
                std::cout << "unrecognized length unit " << length_unit
                          << " in settings.yml, use default mile\n";
            }
        }
        catch(const std::exception& e)
        {
            // do nothing and use default length unit: mile
        }

        try
        {
            auto speed_unit = network["speed_unit"].as<std::string>();
            this->to_lower(speed_unit);

            if (speed_unit == "km/h"s || speed_unit == "kmph"s)
                this->spd_unit_conversion_factor = MPH_TO_KMPH;
            else if (speed_unit == "mph"s)
                this->spd_unit_conversion_factor = 1.0;
            else
            {
                std::cout << "unrecognized speed unit " << speed_unit
                          << " in settings.yml, use default mph\n";
            }
        }
        catch (const std::exception& e)
        {
            // do nothing and use default speed unit: km/h
        }
    }
    catch (const std::exception& e)
    {
        // do nothing
        // use default length unit: mile, speed unit: mph
    }

    // set up ue
    try
    {
        const YAML::Node& ue = settings["user_equilibrium"];
        auto load_columns = ue["load_columns"].as<bool>();
        auto column_gen_num = ue["column_gen_num"].as<unsigned short>();
        auto column_upd_num = ue["column_opd_num"].as<unsigned short>();

        this->update_ue_settings(load_columns, column_gen_num, column_upd_num);

        try
        {
            auto max_cpu_threads = ue["max_cpu_threads"].as<unsigned short>();
            this->max_threads = max_cpu_threads;
        }
        catch (const std::exception& e)
        {
            // do nothing
        }

        const auto& outputs = ue["output"];
        for (const auto& output : outputs)
        {
            try
            {
                auto output_type = output["type"].as<std::string>();
                auto enable = output["enable"].as<bool>();
                // useless
                auto file_name = output["file_name"].as<std::string>();

                this->to_lower(output_type);
                if (output_type == "link_performance"s)
                {
                    this->m_saves_link_perf_ue = enable;
                }
                else if (output_type == "ue_path_flow"s)
                {
                    this->m_saves_path_flow = enable;
                    this->m_includes_path_geometry = output["include_path_geometry"].as<bool>();;
                }
            }
            catch (const std::exception& e)
            {
                // do nothing
            }
        }
    }
    catch (const std::exception& e)
    {
        // do nothing and set up ue with default settings
    }

    uint8_t i = 0;
    const auto& agents = settings["agent_type"];
    for (const auto& a : agents)
    {
        try
        {
            // auto type_ = a["type"];
            auto name = a["name"].as<std::string>();
            if (this->contains_agent_name(name))
            {
                std::cerr << "duplicate agent type found: " << name << '\n';
                continue;
            }

            auto flow_type = a["flow_type"].as<uint8_t>();
            auto pce = a["pce"].as<double>();
            auto vot = a["vot"].as<double>();
            auto ffs = a["free_speed"].as<double>();
            auto use_ffs = a["use_link_ffs"].as<bool>();

            const auto at = new AgentType{i++, name, flow_type, pce, vot, ffs, use_ffs};
            this->ats.push_back(at);
        }
        catch(const std::exception& e)
        {
            // do nothing and move to the next one
        }
    }

    // it is possible that no AgentType is set up
    if (this->ats.empty())
        this->ats.push_back(new AgentType());

    // F03: optional file name override for the departure profile input
    const auto& dtp = settings["departure_time_profiles"];
    if (dtp && dtp["source"])
        this->m_dep_profile_filename = dtp["source"].as<std::string>();

    uint8_t j = 0;
    int entry_no = 0;
    std::vector<int> period_ids;
    const auto& demand_periods = settings["demand_period"];
    for (const auto& dp : demand_periods)
    {
        uint8_t k = 0;
        auto period = dp["period"].as<std::string>();
        auto time_period = dp["time_period"].as<std::string>();

        // F03c: bindings moved to the top-level departure_profile_binding block
        if (dp["departure_profile"])
            throw std::invalid_argument{
                "demand_period." + period + ".departure_profile is no longer supported; "
                "declare the binding in the top-level departure_profile_binding block "
                "(period_id, agent_type, profile_id)"
            };

        // F03c: registry rows stay loaded when inactive; demand is not read
        auto active = dp["active"] ? dp["active"].as<bool>() : true;

        // explicit computational key; falls back to the 1-based entry position
        ++entry_no;
        auto period_id = dp["period_id"] ? dp["period_id"].as<int>() : entry_no;
        if (period_id < 1)
            throw std::invalid_argument{
                "period_id must be a positive integer for demand_period " + period
            };

        for (auto id : period_ids)
        {
            if (id == period_id)
                throw std::invalid_argument{
                    "duplicate period_id " + std::to_string(period_id)
                    + " for demand_period " + period
                };
        }

        period_ids.push_back(period_id);

        const auto& demands = dp["demand"];
        for (const auto& d : demands)
        {
            auto file_name = d["file_name"].as<std::string>();
            auto at_name = d["agent_type"].as<std::string>();
            try
            {
                const auto at = this->get_agent_type(at_name);
                // special event
                std::unique_ptr<SpecialEvent> se = nullptr;
                try
                {
                    const auto& special_event = dp["special_event"];
                    auto enable = special_event["enable"].as<bool>();
                    if (enable)
                    {
                        auto name = special_event["name"].as<std::string>();
                        se = std::make_unique<SpecialEvent>(name);

                        const auto& affected_links = special_event["affected_link"];
                        for (const auto& link : affected_links)
                        {
                            auto link_id = link["link_id"].as<std::string>();
                            auto rr = link["capacity_ratio"].as<double>();
                            se->add_affected_link(link_id, rr);
                        }
                    }
                }
                catch(const std::exception& e)
                {
                    // do nothing
                }

                // copies: the ctor moves the strings, and one settings entry
                // may spawn one DemandPeriod per demand file
                auto period_copy = period;
                auto time_period_copy = time_period;
                const auto dp_ = new DemandPeriod{
                    j++, period_id, active, period_copy, time_period_copy,
                    Demand{k++, file_name, at}, se
                };

                this->dps.push_back(dp_);
            }
            catch(const std::invalid_argument&)
            {
                // malformed time_period from DemandPeriod::setup_time(); fatal
                throw;
            }
            catch(const std::exception& e)
            {
                std::cerr << at_name << " is not existing in settings.yml\n";
            }
        }
    }

    // F03c: period x agent type x profile binding table (the only join
    // between the demand-period registry and the 24h profile library)
    const auto& dpb = settings["departure_profile_binding"];
    if (dpb)
    {
        for (const auto& b : dpb)
        {
            if (!b["period_id"] || !b["profile_id"])
                throw std::invalid_argument{
                    "each departure_profile_binding entry requires period_id and profile_id"
                };

            auto b_pid = parse_period_id_str(b["period_id"].as<std::string>());
            bool known = false;
            for (auto id : period_ids)
            {
                if (id == b_pid)
                {
                    known = true;
                    break;
                }
            }

            if (!known)
                throw std::invalid_argument{
                    "departure_profile_binding references unknown period_id "
                    + std::to_string(b_pid)
                };

            auto b_at = b["agent_type"] ? b["agent_type"].as<std::string>() : ""s;
            if (!b_at.empty())
            {
                try
                {
                    this->get_agent_type(b_at);
                }
                catch (const std::exception&)
                {
                    throw std::invalid_argument{
                        "departure_profile_binding references unknown agent_type " + b_at
                    };
                }
            }

            this->profile_bindings.push_back(
                ProfileBinding{b_pid, b_at, b["profile_id"].as<std::string>()}
            );
        }
    }

    try
    {
        this->validate_demand_periods();
    }
    catch (const std::runtime_error& re)
    {
        std::cerr << re.what() << '\n';
    }

    if (this->dps.empty())
    {
        const auto at = this->ats.front();
        this->dps.push_back(new DemandPeriod{Demand{at}});
    }

    // V1-b: optional root run mode (default smoke). Validation blocks on
    // any unsourced supply or profile - see report_readiness().
    try
    {
        auto mode = settings["run_mode"].as<std::string>();
        this->to_lower(mode);
        if (mode == "validation"s)
            this->run_mode = RunMode::validation;
        else if (mode != "smoke"s)
            throw std::invalid_argument{
                "run_mode must be smoke or validation, got " + mode
            };
    }
    catch (const YAML::Exception& e)
    {
        // absent -> smoke
    }

    try
    {
        const YAML::Node& simulation = settings["simulation"];
        auto run_simu = simulation["enable"].as<bool>();
        if (run_simu)
        {
            auto res = simulation["resolution"].as<unsigned short>();
            auto model = simulation["traffic_flow_model"].as<std::string>();

            this->to_lower(model);
            this->update_simulation_settings(res, model);

            const auto& outputs = simulation["output"];
            for (const auto& output : outputs)
            {
                try
                {
                    auto output_type = output["type"].as<std::string>();
                    auto enable = output["enable"].as<bool>();

                    this->to_lower(output_type);
                    if (output_type == "dynamic_link_performance"s)
                    {
                        this->m_saves_link_perf_dta = enable;
                    }
                    else if (output_type == "agent_trajectory"s)
                    {
                        this->m_saves_agent_trajectory = enable;
                    }
                }
                catch(const std::exception& e)
                {
                    // do nothing and move to the next one
                }
            }
        }
    }
    catch (const std::exception& e)
    {
        // do nothing and set up simulation with default settings
    }

    if (!this->m_saves_path_flow && !this->m_saves_link_perf_ue &&
        (!this->m_enable_simu || (!this->m_saves_agent_trajectory && !this->m_saves_link_perf_dta)))
        this->m_enables_output = false;
}

void NetworkHandle::read_settings()
{
    fs::path file_path = this->input_dir.string() + '/' + "settings.yml";
    if (fs::exists(file_path))
        this->read_settings_yml(file_path.string());
    else
        this->auto_setup();
}

void NetworkHandle::output_columns()
{
    auto writer = miocsv::Writer(output_dir.string() + '/' + this->m_cols_filename);

    writer.write_row_raw("agent_id", "o_zone_id", "d_zone_id", "path_id", "agent_type",
                         "demand_period", "volume", "toll", "travel_time", "distance",
                         "link_sequence", "node_sequence", "geometry");

    size_type i = 0;
    for (const auto& cv : cp.get_column_vecs())
    {
        // oz_no, dz_no, dp_no, at_no
        auto oz_no = std::get<0>(cv.get_key());
        auto dz_no = std::get<1>(cv.get_key());
        auto dp_no = std::get<2>(cv.get_key());
        auto at_no = std::get<3>(cv.get_key());

        auto dp_str = dps[dp_no]->get_period();
        auto at_str = ats[at_no]->get_name();

        for (const auto& col : cv.get_columns())
        {
            if (!col.get_volume())
                continue;

            writer.append(i++);
            writer.append(this->get_zone_id(oz_no));
            writer.append(this->get_zone_id(dz_no));
            writer.append(col.get_no());
            writer.append(at_str);
            writer.append(dp_str);
            writer.append(col.get_volume());
            writer.append(col.get_toll());
            writer.append(col.get_travel_time());
            writer.append(col.get_dist());

            writer.append(this->get_link_path_str(col));
            writer.append(this->get_node_path_str(col));

            if (this->m_includes_path_geometry)
                writer.append(this->get_node_path_coordinates(col), '\n');
            else
                writer.append("", '\n');
        }
    }

    std::cout << "check " << this->m_cols_filename << " in " << output_dir <<  " for UE results\n";
}

void NetworkHandle::output_link_performance_dta()
{
    auto writer = miocsv::Writer(output_dir.string() + '/' + this->m_link_perf_dta_filename);

    writer.write_row_raw("link_id", "from_node_id", "to_node_id", "time_period", "volume",
                         "travel_time",  "waiting_time", "speed", "CA", "CD", "density", "queue");

    // number of simulation intervals in one minute
    const unsigned short num = this->cast_minute_to_interval(1);
    unsigned short dp_no = 0;
    size_type ub = this->get_end_simulation_interval(dp_no);

    for (const auto& link_que : this->link_queues)
    {
        const auto link = link_que.get_link();

        if (!link->get_length())
            continue;

        for (size_type t = 0, e = this->get_simulation_intervals(); t != e; ++t)
        {
            if (t % num)
                continue;

            if (t >= ub)
            {
                // restrict dp_no as we allow user to add buffer time to simulation
                // in addition to the given demand periods
                if (dp_no < this->dps.size() - 1)
                    ub = this->get_end_simulation_interval(++dp_no);
                else
                    ub = this->get_simulation_intervals();
            }

            auto minute = this->cast_interval_to_minute(t);

            writer.append(link->get_id());
            writer.append(this->get_head_node_id(link));
            writer.append(this->get_tail_node_id(link));
            writer.append(this->dps[dp_no]->get_period());
            writer.append(link_que.get_volume(t));
            writer.append(link_que.get_travel_time(t, dp_no));
            writer.append(link_que.get_avg_waiting_time(t));
            writer.append(link_que.get_speed(t, dp_no));
            writer.append(link_que.get_cumulative_arrival(t));
            writer.append(link_que.get_cumulative_departure(t));
            writer.append(link_que.get_density(t));
            writer.append(link_que.get_queue(t, dp_no), '\n');
        }
    }

    std::cout << "check " << this->m_link_perf_dta_filename << " in " << this->output_dir <<  " for link performance under DTA\n";
}

void NetworkHandle::output_link_performance_ue()
{
    auto writer = miocsv::Writer(this->output_dir.string() + '/' + this->m_link_perf_ue_filename);

    writer.write_row_raw("link_id", "from_node_id", "to_node_id", "time_period", "volume",
                         "travel_time", "speed", "VOC", "geometry");

    for (const auto link : this->net.get_links())
    {
        if (!link->get_length())
            continue;

        for (const auto& dp : this->dps)
        {
            auto dp_no = dp->get_no();
            auto tt = link->get_period_travel_time(dp_no);
            auto spd = tt > 0 ? link->get_length() / tt * MINUTES_IN_HOUR : std::numeric_limits<unsigned>::max();

            writer.write_row_raw(link->get_id(), this->get_head_node_id(link), this->get_tail_node_id(link),
                                 dp->get_period(), link->get_period_vol(dp_no), tt, spd, link->get_period_voc(dp_no),
                                 link->get_geometry());
        }
    }

    std::cout << "check " << this->m_link_perf_ue_filename << " in " << this->output_dir <<  " for link performance under UE\n";
}

// S1: project the G5 conditional distributions onto per-bin demand rows,
// D_k = D * p~_k with sum_k D_k == D exactly. This table is the input
// contract S2 vehicleization consumes (largest remainder over `demand`).
// No bindings -> no file, behavior unchanged.
void NetworkHandle::output_departure_bin_demand()
{
    if (this->dep_profiles.empty())
        return;

    auto writer = miocsv::Writer(output_dir.string() + '/' + this->m_dep_bin_filename);
    writer.write_row_raw("period_id", "agent_type", "profile_id", "bin_start_clock",
                         "bin_width_sec", "conditional_weight", "demand");

    char buf[32];
    for (const auto dp_prof : this->dep_profiles)
    {
        // loaded demand for this (period, agent): the same matching rule the
        // G5 audit uses in read_departure_profiles()
        double demand = 0;
        for (const auto dp : this->dps)
        {
            if (dp->get_period_id() != dp_prof->get_period_id())
                continue;

            if (!dp_prof->get_agent_type().empty()
                && dp->get_demands().front().get_agent_type_name() != dp_prof->get_agent_type())
                continue;

            auto it = this->demand_totals.find(dp->get_no());
            if (it != this->demand_totals.end())
                demand += it->second;
        }

        for (const auto& b : dp_prof->get_bins())
        {
            writer.append(dp_prof->get_period_id());
            writer.append(dp_prof->get_agent_type().empty() ? "(all)"s : dp_prof->get_agent_type());
            writer.append(dp_prof->get_id());
            writer.append(format_clock(b.start_min));
            writer.append(static_cast<int>(b.width_min * SECONDS_IN_MINUTE + 0.5));
            // full precision so downstream conservation checks hold to 1e-9
            std::snprintf(buf, sizeof(buf), "%.15g", b.weight);
            writer.append(std::string{buf});
            std::snprintf(buf, sizeof(buf), "%.15g", demand * b.weight);
            writer.append(std::string{buf}, '\n');
        }
    }
}

// S3: the loading contract as a permanent engine artifact. Per (period,
// agent) cohort and per clock minute: realized cumulative departures A_sim
// vs the contract value A_theory = n * F(t) (bound conditional CDF, or
// uniform for unbound periods). Guards the S2a/b/c vehicleization chain as
// a standing gate, independent of any link output.
void NetworkHandle::output_cumulative_departure_audit()
{
    if (this->agents.empty())
        return;

    // cohort agent departure times (minutes) keyed by (dp_no, at_no)
    std::map<std::pair<unsigned short, unsigned short>, std::vector<double>> cohorts;
    for (const auto& agent : this->agents)
        cohorts[{agent.get_demand_period_no(), agent.get_agent_type_no()}]
            .push_back(agent.get_orig_dep_time());

    auto writer = miocsv::Writer(output_dir.string() + '/' + this->m_cum_audit_filename);
    writer.write_row_raw("period_id", "agent_type", "minute", "A_sim",
                         "A_theory", "deviation", "cohort_size");

    for (auto& [key, times] : cohorts)
    {
        const auto dp = this->dps[key.first];
        const auto& at_name = this->ats[key.second]->get_name();
        std::sort(times.begin(), times.end());
        auto n = times.size();

        // the same profile lookup setup_agents uses
        const DepartureProfile* profile = nullptr;
        for (const auto dpr : this->dep_profiles)
        {
            if (dpr->get_period_id() != dp->get_period_id())
                continue;

            if (dpr->get_agent_type().empty() || dpr->get_agent_type() == at_name)
            {
                profile = dpr;
                break;
            }
        }

        auto st = dp->get_start_time();
        auto et = dp->get_end_time();
        std::vector<double>::size_type served = 0;
        for (auto m = st; m != et; ++m)
        {
            // A_sim: departures through the end of minute m
            while (served < n && times[served] < m + 1)
                ++served;

            // A_theory: n * F at the end of minute m
            double f = 0;
            if (profile)
            {
                for (const auto& b : profile->get_bins())
                {
                    if (b.start_min + b.width_min <= m + 1)
                        f += b.weight;
                    else if (b.start_min < m + 1)
                        f += b.weight * (m + 1 - b.start_min) / b.width_min;
                }
            }
            else
                f = std::min(1.0, static_cast<double>(m + 1 - st) / dp->get_duration());

            char buf[32];
            writer.append(dp->get_period_id());
            writer.append(at_name);
            writer.append(m);
            writer.append(served);
            std::snprintf(buf, sizeof(buf), "%.6f", n * f);
            writer.append(std::string{buf});
            std::snprintf(buf, sizeof(buf), "%.6f", served - n * f);
            writer.append(std::string{buf});
            writer.append(n, '\n');
        }
    }
}

void NetworkHandle::output_trajectories()
{
    auto writer = miocsv::Writer(this->output_dir.string() + '/' + this->m_traj_filename);

    writer.write_row_raw("agent_id", "o_zone_id", "d_zone_id", "dep_time", "arr_time", "trip_completed",
                         "travel_time", "PCE", "travel_distance", "node_path", "geometry", "time_sequence");

    for (const auto& agent : this->agents)
    {
        // S0d: every agent is emitted. The former (dep_time, OD) dedup
        // silently suppressed same-minute same-OD vehicles - most of the
        // fleet under batched departures - making the audit trail
        // structurally incomplete.
        auto dt = agent.get_orig_dep_time();
        auto at = this->get_real_time(agent.get_dest_arr_interval());
        char trip_status = agent.completes_trip() ? 'c' : 'n';

        std::string time_seq_str;
        // move assignment
        const auto vec = agent.get_time_sequence();
        for (size_type i = 0, e = vec.size() - 1; i != e; ++i)
        {
            auto t = this->get_real_time(vec[i]);
            time_seq_str += this->get_time_stamp(t);
            time_seq_str += ';';
        }
        // the last one without trailing ';'
        auto t = this->get_real_time(vec.back());
        time_seq_str += this->get_time_stamp(t);

        const auto& col = *agent.get_column();

        writer.append(agent.get_no());
        writer.append(agent.get_orig_zone_no());
        writer.append(agent.get_dest_zone_no());
        writer.append(this->get_time_stamp(dt));
        writer.append(this->get_time_stamp(at));
        writer.append(trip_status);
        writer.append(this->cast_interval_to_minute_double(agent.get_travel_interval()));
        writer.append(agent.get_pce());
        writer.append(col.get_dist());
        writer.append(this->get_node_path_str(col));
        writer.append(this->get_node_path_coordinates(col));
        writer.append(time_seq_str, '\n');
    }

    std::cout << "check " << this->m_traj_filename << " in " << this->output_dir <<  " for agent trajectory under DTA\n";
}

// V1-d: the four required output artifacts (OPENDTA_V1_MVP_SPEC.md section
// 6), written from ONE metric pass so P, v_T2 and the N-accounting cannot
// drift between files. Nothing here alters an existing output: the added
// mu / spillback columns live in the new link_time_series.csv, exactly as
// the spec names it, leaving the frozen baselines byte-identical.
void NetworkHandle::output_run_reports()
{
    const unsigned short num = this->cast_minute_to_interval(1);
    const auto n_intvl = this->get_simulation_intervals();
    const double intvl_hours = static_cast<double>(this->simu_res) / SECONDS_IN_HOUR;

    auto lts = miocsv::Writer(this->output_dir.string() + "/link_time_series.csv");
    lts.write_row_raw("link_id", "from_node_id", "to_node_id", "time_period",
                      "minute", "volume", "inflow", "outflow", "mu_vph",
                      "travel_time", "speed", "CA", "CD", "density", "queue",
                      "spillback_flag");

    std::vector<QueueEpisode> episodes;
    double vmt = 0;
    double vht = 0;
    size_type remaining = 0;
    size_type queued_links = 0;
    size_type spillback_links = 0;

    for (const auto& lq : this->link_queues)
    {
        const auto link = lq.get_link();

        // VMT / VHT / terminal occupancy over EVERY interval (not just the
        // minute samples): CD(T) counts the vehicles that traversed the link,
        // and sum_t (CA - CD) is the exact N-curve area, i.e. time in system
        vmt += static_cast<double>(lq.get_cumulative_departure(n_intvl - 1))
             * link->get_length();
        for (size_type t = 0; t != n_intvl; ++t)
        {
            vht += static_cast<double>(lq.get_cumulative_arrival(t)
                                       - lq.get_cumulative_departure(t)) * intvl_hours;
        }

        remaining += lq.get_cumulative_arrival(n_intvl - 1)
                   - lq.get_cumulative_departure(n_intvl - 1);

        if (!link->get_length())
            continue;

        // the demand-period index must restart with every link - it indexes
        // the per-period fftt used by travel_time / speed / queue
        unsigned short dp_no = 0;
        size_type ub = this->get_end_simulation_interval(dp_no);
        bool in_episode = false;
        bool link_spilled = false;
        bool link_queued = false;
        QueueEpisode ep {};

        for (size_type t = 0; t != n_intvl; t += num)
        {
            if (t >= ub)
            {
                if (dp_no < this->dps.size() - 1)
                    ub = this->get_end_simulation_interval(++dp_no);
                else
                    ub = n_intvl;
            }

            auto minute = this->cast_interval_to_minute(t);
            auto ca = lq.get_cumulative_arrival(t);
            auto cd = lq.get_cumulative_departure(t);
            auto prev = t >= num ? t - num : 0;
            auto inflow = t >= num ? ca - lq.get_cumulative_arrival(prev) : ca;
            auto outflow = t >= num ? cd - lq.get_cumulative_departure(prev) : cd;

            // the mu the engine was GIVEN, summed over this minute's
            // intervals, so the user can read back the supply the engine used
            // against the supply they wrote in link_supply.csv (V1-c). The
            // realized service is the separate `outflow` column.
            double served = 0;
            for (size_type i = t, e = std::min(t + num, n_intvl); i != e; ++i)
                served += lq.get_mu_rate(i);

            double mu_vph = served * MINUTES_IN_HOUR;

            // the spillback test is the engine's OWN acceptance test
            // (simulation.cpp transfer gate), so the flag cannot disagree
            // with the physics that produced it; the point-queue model has
            // no spatial constraint, hence no spillback by construction
            bool spill = false;
            if (this->uses_spatial_queue_model())
                spill = lq.get_waiting_vehicle_num_sq(t) > lq.get_spatial_capacity();
            else if (this->uses_kinematic_wave_model())
                spill = lq.get_waiting_vehicle_num_kw(t) > lq.get_spatial_capacity();

            if (spill)
                link_spilled = true;

            auto queue = lq.get_queue(t, dp_no);
            auto speed = lq.get_speed(t, dp_no);

            lts.append(link->get_id());
            lts.append(this->get_head_node_id(link));
            lts.append(this->get_tail_node_id(link));
            lts.append(this->dps[dp_no]->get_period());
            lts.append(minute);
            lts.append(lq.get_volume(t));
            lts.append(inflow);
            lts.append(outflow);
            lts.append(mu_vph);
            lts.append(lq.get_travel_time(t, dp_no));
            lts.append(speed);
            lts.append(ca);
            lts.append(cd);
            lts.append(lq.get_density(t));
            lts.append(queue);
            lts.append(spill ? 1 : 0, '\n');

            // congestion episodes: contiguous minutes with a nonempty queue
            if (queue > 0)
            {
                link_queued = true;
                if (!in_episode)
                {
                    in_episode = true;
                    ep = QueueEpisode{link->get_id(), minute, minute, 0, speed, 0};
                }

                ep.end_min = minute;
                ep.max_queue = std::max(ep.max_queue, queue);
                ep.v_t2_mph = std::min(ep.v_t2_mph, speed);
                ep.total_delay_veh_min += static_cast<double>(queue);
            }
            else if (in_episode)
            {
                in_episode = false;
                episodes.push_back(ep);
            }
        }

        if (in_episode)
            episodes.push_back(ep);

        if (link_queued)
            ++queued_links;

        if (link_spilled)
            ++spillback_links;
    }

    // P and v_T2 both come from the SAME longest episode, so the two
    // scalars always describe one bottleneck
    unsigned p_max = 0;
    double v_t2 = 0;
    std::string p_max_link;
    for (const auto& e : episodes)
    {
        unsigned dur = e.end_min - e.start_min + 1;
        if (dur > p_max)
        {
            p_max = dur;
            v_t2 = e.v_t2_mph;
            p_max_link = e.link_id;
        }
    }

    auto qts = miocsv::Writer(this->output_dir.string() + "/queue_time_series.csv");
    qts.write_row_raw("link_id", "episode_id", "start_minute", "end_minute",
                      "duration_minutes", "max_queue", "v_T2_mph",
                      "total_delay_veh_min");
    for (std::vector<QueueEpisode>::size_type i = 0; i != episodes.size(); ++i)
    {
        const auto& e = episodes[i];
        qts.append(e.link_id);
        qts.append(i + 1);
        qts.append(e.start_min);
        qts.append(e.end_min);
        qts.append(e.end_min - e.start_min + 1);
        qts.append(e.max_queue);
        qts.append(e.v_t2_mph);
        qts.append(e.total_delay_veh_min, '\n');
    }

    // PT-6 N-accounting. `entered` mirrors the engine's own loading loop;
    // `remaining` is recomputed INDEPENDENTLY from the link N-curves above,
    // so `entered == exited + remaining` is a real cross-source check on
    // vehicle loss, not a restatement of one counter.
    size_type generated = this->agents.size();
    size_type entered = 0;
    size_type exited = 0;
    double agent_tt_hours = 0;
    for (size_type t = 0; t != n_intvl; ++t)
    {
        if (!this->has_dep_agents(t))
            continue;

        for (auto a_no : this->get_agents_at_interval(t))
        {
            if (this->get_agent(a_no).get_link_num())
                ++entered;
        }
    }

    // NOT completes_trip(): that predicate reads the uninitialized sentinel
    // as a completion and would report every stranded vehicle as arrived
    // (see the defect note in demand.h). A vehicle has left the network only
    // if its final-link departure actually fell inside the horizon.
    for (const auto& a : this->agents)
    {
        if (a.get_final_dep_interval() < n_intvl)
        {
            ++exited;
            agent_tt_hours += this->cast_interval_to_minute_double(a.get_travel_interval())
                            / MINUTES_IN_HOUR;
        }
    }

    size_type not_entered = generated > entered ? generated - entered : 0;
    bool conservation_ok = entered == exited + remaining;

    auto cons = miocsv::Writer(this->output_dir.string() + "/conservation_report.csv");
    cons.write_row_raw("check", "scope", "expected", "actual", "abs_diff",
                       "tolerance", "status");

    auto write_check = [&cons](const std::string& name, const std::string& scope,
                               double expected, double actual, double tol) {
        double diff = std::fabs(expected - actual);
        cons.append(name);
        cons.append(scope);
        cons.append(expected);
        cons.append(actual);
        cons.append(diff);
        cons.append(tol);
        cons.append(diff <= tol ? "PASS" : "FAIL", '\n');
    };

    write_check("vehicle_accounting_PT6", "network",
                static_cast<double>(entered),
                static_cast<double>(exited + remaining), 0);

    // the N-curve area must equal the sum of agent travel times - two
    // independent bookkeepings of the same physical time. Only meaningful
    // once every vehicle has finished; otherwise the in-network time has no
    // trajectory counterpart yet.
    if (remaining == 0 && not_entered == 0)
        write_check("VHT_link_vs_agent", "network", vht, agent_tt_hours, 0.02);
    else
    {
        cons.append("VHT_link_vs_agent");
        cons.append("network");
        cons.append(vht);
        cons.append(agent_tt_hours);
        cons.append("");
        cons.append("");
        cons.append("SKIPPED-VEHICLES_STILL_IN_NETWORK", '\n');
    }

    for (const auto& lq : this->link_queues)
    {
        const auto link = lq.get_link();
        if (!link->get_length())
            continue;

        auto ca = lq.get_cumulative_arrival(n_intvl - 1);
        auto cd = lq.get_cumulative_departure(n_intvl - 1);
        // a link can never have discharged more than it received
        write_check("terminal_occupancy_nonnegative", "link " + link->get_id(),
                    1, ca >= cd ? 1 : 0, 0);

        bool monotone = true;
        for (size_type t = 1; t != n_intvl; ++t)
        {
            if (lq.get_cumulative_departure(t) < lq.get_cumulative_departure(t - 1))
            {
                monotone = false;
                break;
            }
        }

        write_check("CD_monotone", "link " + link->get_id(), 1, monotone ? 1 : 0, 0);
    }

    std::chrono::duration<double> elapsed = std::chrono::steady_clock::now() - this->wall_start;

    std::ofstream f((this->output_dir / "run_summary.json").string());
    f << "{\n \"run_mode\": \""
      << (this->run_mode == RunMode::validation ? "validation" : "smoke")
      << "\",\n \"validation_eligible\": " << (this->validation_eligible ? "true" : "false")
      << ",\n \"used_default_mu\": " << (this->used_default_mu ? "true" : "false")
      << ",\n \"used_default_profile\": " << (this->used_default_profile ? "true" : "false")
      << ",\n \"vehicles\": {"
      << "\n  \"generated\": " << generated
      << ",\n  \"entered\": " << entered
      << ",\n  \"not_entered\": " << not_entered
      << ",\n  \"exited\": " << exited
      << ",\n  \"remaining\": " << remaining
      << ",\n  \"conservation_ok\": " << (conservation_ok ? "true" : "false")
      << "\n },\n \"network\": {"
      << "\n  \"VMT\": " << vmt
      << ",\n  \"VHT\": " << vht
      << ",\n  \"avg_speed_mph\": " << (vht > 0 ? vmt / vht : 0)
      << ",\n  \"P_max_minutes\": " << p_max
      << ",\n  \"P_max_link_id\": \"" << p_max_link << '"'
      << ",\n  \"v_T2_mph\": " << v_t2
      << ",\n  \"queued_link_count\": " << queued_links
      << ",\n  \"spillback_link_count\": " << spillback_links
      << "\n },\n \"runtime_seconds\": " << elapsed.count()
      << ",\n \"all_gate_status\": {";
    for (std::vector<std::pair<std::string, std::string>>::size_type i = 0;
         i != this->gate_status.size(); ++i)
    {
        f << (i ? ",\n  " : "\n  ") << '"' << this->gate_status[i].first
          << "\": \"" << this->gate_status[i].second << '"';
    }

    f << "\n }\n}\n";

    std::cout << "check run_summary.json, link_time_series.csv, "
                 "queue_time_series.csv and conservation_report.csv in "
              << this->output_dir << '\n';
}

void NetworkHandle::setup_working_dirs(const char* argv1, const char* argv2)
{
    fs::path tmp_input_dir = argv1;
    fs::path tmp_output_dir = argv2;

    const bool exists_input = fs::exists(tmp_input_dir);
    const bool exists_output = fs::exists(tmp_output_dir);

    if (exists_input && exists_output)
    {
        this->input_dir = tmp_input_dir;
        this->output_dir = tmp_output_dir;
    }
    else if (exists_input && !exists_output)
    {
        this->input_dir = tmp_input_dir;
        this->output_dir = tmp_input_dir;
    }
    else if (!exists_input && exists_output)
    {
        this->output_dir = tmp_input_dir;
    }
    else
    {
        std::cout << "INVALID DIRECTORIES! USE THE CURRENT PATH " << fs::current_path() << '\n';
    }
}
