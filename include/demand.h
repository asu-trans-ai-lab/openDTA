/**
 * @file demand.h, part of the project OpenDTA under Apache License 2.0
 * @author jdlph (jdlph@hotmail.com) and xzhou99 (xzhou74@asu.edu)
 * @brief Definitions of classes related to demand
 *
 * @copyright Copyright (c) 2023 -2025 Peiheng Li, Ph.D. and Xuesong (Simon) Zhou, Ph.D.
 */

#ifndef GUARD_DEMAND_H
#define GUARD_DEMAND_H

#include <global.h>

#include <map>
#include <memory>
#include <vector>

namespace transoms
{
class Agent {
public:
    Agent() = delete;

    Agent(size_type no_, uint8_t at_no_, uint8_t dp_no_,
          unsigned short oz_no_, unsigned short dz_no_, const Column* c = nullptr)
        : no {no_}, at_no {at_no_}, dp_no {dp_no_}, oz_no {oz_no_}, dz_no {dz_no_},
          col {c}, pce {1}
    {
        initialize_intervals();
    }

    Agent(const Agent&) = delete;
    Agent& operator=(const Agent&) = delete;

    Agent(Agent&&) noexcept = default;
    Agent& operator=(Agent&&) = delete;

    ~Agent() = default;

    // A vehicle's final-link departure is only a completion if it was
    // actually recorded. The former test was `front() > 0`, but
    // initialize_intervals() fills dep_intvls with size_type::max() and the
    // sentinel is > 0 - so every vehicle that never reached its final link
    // reported as arrived. Callers that know the simulation horizon must
    // ALSO range-check get_final_dep_interval() against it: see the note
    // there for the second way this value is not a completion.
    bool completes_trip() const
    {
        return dep_intvls.front() != std::numeric_limits<size_type>::max();
    }

    /**
     * @brief V1-d: the interval at which this vehicle departed its final link.
     *
     * Two ways this is NOT a completion, both of which the caller must
     * range-check against the simulation horizon:
     * - size_type::max(), the initialize_intervals() sentinel, when the
     *   vehicle never reached the final link at all;
     * - a value past the last simulated interval, because
     *   increment_dep_interval() schedules arrival + waiting and that sum can
     *   land beyond the horizon. The link N-curves correctly never discharge
     *   such a vehicle: it is still in the network when the clock stops.
     *
     * completes_trip() above now covers the first case; the horizon check
     * cannot live there because Agent does not know the horizon, so every
     * caller that reports completion must apply it - see
     * NetworkHandle::output_trajectories() and output_run_reports().
     */
    size_type get_final_dep_interval() const
    {
        return dep_intvls.front();
    }

    auto get_agent_type_no() const
    {
        return at_no;
    }

    const Column* get_column() const
    {
        return col;
    }

    auto get_demand_period_no() const
    {
        return dp_no;
    }

    auto get_dest_zone_no() const
    {
        return dz_no;
    }

    auto get_orig_zone_no() const
    {
        return oz_no;
    }

    auto get_od() const
    {
        return std::make_pair(oz_no, dz_no);
    }

    size_type get_no() const
    {
        return no;
    }

    double get_pce() const
    {
        return pce;
    }

    // simulation
    bool reaches_last_link() const
    {
        return curr_link_no == 0;
    }

    auto get_arr_interval() const
    {
        return arr_intvls[curr_link_no];
    }

    auto get_dep_interval() const
    {
        return dep_intvls[curr_link_no];
    }

    size_type get_next_link_no() const
    {
        return get_link_path()[curr_link_no - 1];
    }

    size_type get_dest_arr_interval() const
    {
        auto i = get_dep_interval();
        if (i < std::numeric_limits<size_type>::max())
            return i;

        return dep_intvls[curr_link_no + 1];
    }

    double get_orig_dep_time() const
    {
        return dep_time;
    }

    size_type get_orig_dep_interval() const
    {
        return dep_intvls.back();
    }

    size_type get_travel_interval() const
    {
        return get_dest_arr_interval() - arr_intvls.back();
    }

    void move_to_next_link()
    {
        if (curr_link_no > 0)
            --curr_link_no;
    }

    void set_arr_interval(unsigned i, size_type increment = 0)
    {
        arr_intvls[curr_link_no - increment] = i;
    }

    void set_dep_interval(unsigned i)
    {
        dep_intvls[curr_link_no] = i;
    }

    void set_dep_time(double t)
    {
        dep_time = t;
    }

    // can be combined with set_arr_interval()?
    void set_orig_arr_interval(unsigned i)
    {
        arr_intvls.back() = i;
    }

    void increment_dep_interval(size_type i)
    {
        dep_intvls[curr_link_no] = arr_intvls[curr_link_no] + i;
    }

    const std::vector<size_type>& get_link_path() const;

    std::vector<size_type>::size_type get_link_num() const;
    size_type get_first_link_no() const;

    std::vector<size_type> get_time_sequence() const;

private:
    void initialize_intervals();

private:
    size_type no;

    uint8_t at_no;
    uint8_t dp_no;

    unsigned short oz_no;
    unsigned short dz_no;

    const Column* col;

    double pce;

    // simulation
    size_type curr_link_no;
    double dep_time;

    std::vector<size_type> arr_intvls;
    std::vector<size_type> dep_intvls;
};

class AgentType {
public:
    AgentType() : no {0}, name {"auto"}, flow_type {0}, pce {1},
                  vot {10}, ffs {60}, is_link_ffs {true}
    {
    }

    AgentType(uint8_t no_, std::string& name_, uint8_t flow_type_,
              double pce_, double vot_,  double ffs_, bool use_link_ffs_)
        : no {no_}, name {std::move(name_)}, flow_type {flow_type_}, pce {pce_},
          vot {vot_}, ffs {ffs_}, is_link_ffs {use_link_ffs_}
    {
    }

    AgentType(const AgentType&) = delete;
    AgentType& operator=(const AgentType&) = delete;

    AgentType(AgentType&&) = delete;
    AgentType& operator=(AgentType&&) = delete;

    ~AgentType() = default;

    auto get_no() const
    {
        return no;
    }

    auto get_flow_type() const
    {
        return flow_type;
    }

    auto get_ffs() const
    {
        return ffs;
    }

    const std::string& get_name() const
    {
        return name;
    }

    auto get_pce() const
    {
        return pce;
    }

    auto get_vot() const
    {
        return vot;
    }

    bool use_link_ffs() const
    {
        return is_link_ffs;
    }

public:
    static const std::string& get_default_name()
    {
        return AT_DEFAULT_NAME;
    }

    static const std::string& get_legacy_name()
    {
        return AT_LEGACY_NAME;
    }

private:
    uint8_t no;
    std::string name;

    uint8_t flow_type;
    double pce;
    double vot;

    double ffs;
    bool is_link_ffs;
};

class Demand {
public:
    Demand() = delete;

    explicit Demand(const AgentType* at_) : at {at_}
    {
    }

    Demand(uint8_t no_, std::string& filename_, const AgentType* at_)
        : no {no_}, filename {std::move(filename_)}, at {at_}
    {
    }

    Demand(const Demand&) = default;
    Demand& operator=(const Demand&) = delete;

    Demand(Demand&&) noexcept = default;
    Demand& operator=(Demand&&) = delete;

    ~Demand() = default;

    auto get_no() const
    {
        return no;
    }

    const std::string& get_agent_type_name() const
    {
        return at->get_name();
    }

    auto get_agent_type_no() const
    {
        return at->get_no();
    }

    const std::string& get_file_name() const
    {
        return filename;
    }

private:
    uint8_t no = 0;
    std::string filename = "demand.csv";

    const AgentType* at;
};

// F03c: a per-binding conditional departure distribution derived from a
// 24-hour library profile clipped to one demand-period window and
// renormalized (weights sum to 1 by construction). Nothing consumes it
// until vehicle generation (F04).
class DepartureProfile {
public:
    struct Bin {
        // folded time of day in minutes; width in minutes; conditional weight
        double start_min;
        double width_min;
        double weight;
    };

    DepartureProfile() = delete;

    DepartureProfile(std::string id_, int period_id_, std::string agent_type_,
                     std::vector<Bin>&& bins_, double window_mass_)
        : id {std::move(id_)}, period_id {period_id_}, agent_type {std::move(agent_type_)},
          bins {std::move(bins_)}, window_mass {window_mass_}
    {
    }

    DepartureProfile(const DepartureProfile&) = delete;
    DepartureProfile& operator=(const DepartureProfile&) = delete;

    DepartureProfile(DepartureProfile&&) = delete;
    DepartureProfile& operator=(DepartureProfile&&) = delete;

    ~DepartureProfile() = default;

    const std::string& get_id() const
    {
        return id;
    }

    auto get_period_id() const
    {
        return period_id;
    }

    // empty means the binding applies to every agent type of the period
    const std::string& get_agent_type() const
    {
        return agent_type;
    }

    const std::vector<Bin>& get_bins() const
    {
        return bins;
    }

    // S_r: raw 24h profile mass inside the period window before renormalization
    auto get_window_mass() const
    {
        return window_mass;
    }

private:
    std::string id;
    int period_id;
    std::string agent_type;

    std::vector<Bin> bins;
    double window_mass;
};

// F03c: one row of the settings.yml departure_profile_binding block —
// the only join between demand periods and the 24h profile library
struct ProfileBinding {
    int period_id;
    std::string agent_type;  // empty = all agent types of the period
    std::string profile_id;
};

class DemandPeriod {
public:
    DemandPeriod() : no {0}, period_id {1}, active {true},
                     period {"AM"}, time_period {"0700-0800"}, se {nullptr}
    {
    }

    explicit DemandPeriod(Demand&& dem) : DemandPeriod()
    {
        ds.push_back(dem);
    }

    DemandPeriod(uint8_t no_, int period_id_, bool active_,
                 std::string& period_, std::string& time_period_,
                 Demand&& dem, std::unique_ptr<SpecialEvent>& se_)
        : no {no_}, period_id {period_id_}, active {active_},
          period {std::move(period_)}, time_period {std::move(time_period_)}, se {std::move(se_)}
    {
        ds.push_back(std::move(dem));
        setup_time();
    }

    DemandPeriod(const DemandPeriod&) = delete;
    DemandPeriod& operator=(const DemandPeriod&) = delete;

    DemandPeriod(DemandPeriod&&) = delete;
    DemandPeriod& operator=(DemandPeriod&&) = delete;

    ~DemandPeriod() = default;

    auto get_no() const
    {
        return no;
    }

    // explicit computational key from settings.yml (period_id); falls back to
    // the 1-based position of the demand_period entry when not specified
    auto get_period_id() const
    {
        return period_id;
    }

    const std::string& get_period() const
    {
        return period;
    }

    const std::string& get_time_period() const
    {
        return time_period;
    }

    // F03c: registry rows stay loaded when inactive, but their demand files
    // are not read and they produce no columns or agents
    bool is_active() const
    {
        return active;
    }

    const auto& get_demands() const
    {
        return ds;
    }

    const auto& get_special_event() const
    {
        return se;
    }

    // minute as time of day
    unsigned short get_start_time() const
    {
        return start_time;
    }

    unsigned short get_end_time() const
    {
        return start_time + dur;
    }

    unsigned short get_duration() const
    {
        return dur;
    }

    bool contain_iter_no(unsigned short iter_no) const;
    double get_cap_ratio(const std::string& link_id, unsigned short iter_no) const;

private:
    void setup_time();
    unsigned short to_minutes(const std::string& t);

private:
    uint8_t no;
    int period_id;
    bool active;

    std::string period;
    std::string time_period;

    unsigned short start_time = 420;
    unsigned short dur = 60;

    std::vector<Demand> ds;
    const std::unique_ptr<SpecialEvent> se;
};

} // namespace transoms

#endif