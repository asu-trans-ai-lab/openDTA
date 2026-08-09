/**
 * @file self_test_simulation.cpp
 * @brief OpenDTA simulation self-test harness (Level B: whole-engine cases)
 *
 * Thin test driver over PRODUCTION OpenDTA classes: it re-implements no
 * physics and no loading logic. It runs the tiny bundled datasets under
 * dev/self_test_simulation/cases/ through the real NetworkHandle pipeline,
 * parses the real output files, and asserts against the expected truth
 * frozen in simulation_self_test.yml / expected/.
 *
 * Exit code: 0 = all enabled cases PASS, 1 = any FAIL.
 *
 * Usage: OpenDTA_self_test [self_test_root]
 *   self_test_root defaults to "." and must contain cases/ and expected/.
 */

#include <global.h>
#include <handles.h>

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace transoms;

namespace {

int checks_run = 0;
int checks_failed = 0;

void check(bool ok, const std::string& what)
{
    ++checks_run;
    if (!ok)
    {
        ++checks_failed;
        std::cout << "  FAIL  " << what << '\n';
    }
    else
        std::cout << "  ok    " << what << '\n';
}

std::string read_file(const std::string& path)
{
    std::ifstream ifs {path, std::ios::binary};
    std::ostringstream oss;
    oss << ifs.rdbuf();
    return oss.str();
}

std::vector<std::string> split_csv(const std::string& line)
{
    std::vector<std::string> out;
    std::string field;
    std::istringstream iss {line};
    while (std::getline(iss, field, ','))
        out.push_back(field);

    return out;
}

// run the production pipeline exactly as main.cpp does
void run_engine(const std::string& input_dir, const std::string& output_dir)
{
    NetworkHandle nh;
    nh.setup_working_dirs(input_dir.c_str(), output_dir.c_str());

    nh.read_settings();
    nh.read_network();

    if (nh.uses_existing_columns())
        nh.load_columns();
    else
        nh.read_demands();

    nh.read_departure_profiles();
    nh.find_ue();

    if (nh.enables_simulation())
        nh.run_simulation();

    if (nh.enables_output())
    {
        if (nh.saves_link_performance_ue())
            nh.output_link_performance_ue();

        if (nh.saves_ue_path_flow())
            nh.output_columns();

        if (nh.enables_simulation())
        {
            if (nh.saves_link_performance_dta())
                nh.output_link_performance_dta();

            if (nh.saves_trajectory())
                nh.output_trajectories();
        }
    }
}

// ST00_F6_FREEFLOW: free-flow TT/speed on every row + repeat determinism.
// Expected truth: simulation_self_test.yml / expected/ST00_expected.csv
// (1-mile 60-mph link: TT = 1.0 min, speed = 60 mph, no queue anywhere).
bool run_st00(const std::string& root)
{
    std::cout << "case ST00_F6_FREEFLOW\n";

    const std::string input = root + "/cases/ST00_freeflow_tt/";
    constexpr int repeats = 3;
    std::vector<std::string> perf_dumps;
    std::vector<std::string> traj_dumps;

    for (int r = 1; r <= repeats; ++r)
    {
        const std::string out = root + "/output/ST00/r" + std::to_string(r) + '/';
        // the engine silently redirects output to the input dir when the
        // output dir does not exist - create it first
        std::filesystem::create_directories(out);
        run_engine(input, out);
        perf_dumps.push_back(read_file(out + "link_performance_dta.csv"));
        traj_dumps.push_back(read_file(out + "trajectories.csv"));
    }

    check(!perf_dumps.front().empty(), "link_performance_dta.csv produced");
    check(!traj_dumps.front().empty(), "trajectories.csv produced");

    for (int r = 1; r < repeats; ++r)
    {
        check(perf_dumps[r] == perf_dumps[0],
              "run " + std::to_string(r + 1) + " link_performance_dta.csv byte-identical to run 1");
        check(traj_dumps[r] == traj_dumps[0],
              "run " + std::to_string(r + 1) + " trajectories.csv byte-identical to run 1");
    }

    // analytical assertion: EVERY row of the (queue-free) case reports
    // free-flow travel time and speed
    constexpr double tt_gold = 1.0;    // minutes
    constexpr double spd_gold = 60.0;  // mph
    std::istringstream iss {perf_dumps[0]};
    std::string line;
    std::getline(iss, line);  // header
    std::size_t rows = 0;
    std::size_t bad_tt = 0;
    std::size_t bad_spd = 0;
    std::string first_bad;
    while (std::getline(iss, line))
    {
        if (line.empty())
            continue;

        auto f = split_csv(line);
        if (f.size() < 8)
            continue;

        ++rows;
        // columns: ...,volume(4),travel_time(5),waiting_time(6),speed(7),...
        double tt = std::atof(f[5].c_str());
        double spd = std::atof(f[7].c_str());
        bool tt_ok = std::isfinite(tt) && std::fabs(tt - tt_gold) <= 1e-6;
        bool spd_ok = std::isfinite(spd) && std::fabs(spd - spd_gold) <= 1e-4;
        if (!tt_ok)
            ++bad_tt;

        if (!spd_ok)
            ++bad_spd;

        if ((!tt_ok || !spd_ok) && first_bad.empty())
            first_bad = line;
    }

    check(rows > 0, "output has data rows");
    check(bad_tt == 0, "travel_time == 1.0 min on all " + std::to_string(rows)
                       + " rows (" + std::to_string(bad_tt) + " bad)");
    check(bad_spd == 0, "speed == 60 mph on all " + std::to_string(rows)
                        + " rows (" + std::to_string(bad_spd) + " bad)");
    if (!first_bad.empty())
        std::cout << "  first offending row: " << first_bad << '\n';

    return checks_failed == 0;
}

} // namespace

int main(int argc, char* argv[])
try
{
    const std::string root = argc > 1 ? argv[1] : ".";

    std::cout << "==== OpenDTA Simulation Self Test ====\n"
              << "root: " << root << "\n\n";

    run_st00(root);
    // ST01 (profile loading), ST02 (analytical point queue), ST03 (tandem)
    // are declared in simulation_self_test.yml with enabled: false and are
    // activated as features S1-S6 land.

    std::cout << "\n" << checks_run << " checks, " << checks_failed << " failed: "
              << (checks_failed == 0 ? "PASS" : "FAIL") << '\n';

    return checks_failed == 0 ? 0 : 1;
}
catch (const std::exception& e)
{
    std::cerr << "self test terminated: " << e.what() << '\n';
    return 1;
}
