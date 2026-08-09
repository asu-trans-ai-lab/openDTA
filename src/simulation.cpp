/**
 * @file simulation.cpp, part of the project OpenDTA under Apache License 2.0
 * @author jdlph (jdlph@hotmail.com) and xzhou99 (xzhou74@asu.edu)
 * @brief Implementations of simulation-based Dynamic Traffic Assignment (DTA)
 *
 * @copyright Copyright (c) 2023 - 2025 Peiheng Li, Ph.D. and Xuesong (Simon) Zhou, Ph.D.
 */

#include <handles.h>

#include <cmath>
#include <iostream>

using namespace transoms;

inline const std::vector<size_type>& Agent::get_link_path() const
{
    return col->get_links();
}

inline std::vector<size_type>::size_type Agent::get_link_num() const
{
    return col->get_link_num();
}

inline size_type Agent::get_first_link_no() const
{
    return col->get_first_link_no();
}

std::vector<size_type> Agent::get_time_sequence() const
{
    std::vector<size_type> vec;
    vec.push_back(arr_intvls.back());

    for (auto it = dep_intvls.rbegin(), end = dep_intvls.rend(); it != end; ++it)
    {
        auto i = *it;
        if (i == std::numeric_limits<size_type>::max())
            break;

        vec.push_back(i);
    }

    return vec;
}

void Agent::initialize_intervals()
{
    // throw an error or terminate?
    if (!col)
        return;

    auto n = col->get_link_num();

    arr_intvls.resize(n, std::numeric_limits<size_type>::max());
    dep_intvls.resize(n, std::numeric_limits<size_type>::max());
    curr_link_no = n - 1;
}

unsigned short NetworkHandle::cast_interval_to_minute(size_type i) const
{
    return std::floor(i * this->simu_res / SECONDS_IN_MINUTE);
}

size_type NetworkHandle::cast_minute_to_interval(unsigned short m) const
{
    return std::floor(m * SECONDS_IN_MINUTE / this->simu_res);
}

size_type NetworkHandle::get_simulation_intervals() const
{
    return this->cast_minute_to_interval(this->simu_dur);
}

const std::vector<size_type>& NetworkHandle::get_agents_at_interval(size_type i) const
{
    return this->td_agents.at(i);;
}

Agent& NetworkHandle::get_agent(size_type no)
{
    return this->agents[no];
}

const Agent& NetworkHandle::get_agent(size_type no) const
{
    return this->agents[no];
}

LinkQueue& NetworkHandle::get_link_queue(size_type i)
{
    return this->link_queues[i];
}

// this requires that time periods are consecutive
size_type NetworkHandle::get_beg_simulation_interval(unsigned short k) const
{
    if (!k)
        return 0;

    auto st = this->dps[0]->get_start_time();
    auto et = this->dps[k]->get_start_time();

    return this->cast_minute_to_interval(et - st);
}

size_type NetworkHandle::get_end_simulation_interval(unsigned short k) const
{
    auto st = this->dps[0]->get_start_time();
    auto et = this->dps[k]->get_end_time();

    return this->cast_minute_to_interval(et - st);
}

double NetworkHandle::get_real_time(size_type i) const
{
    return this->cast_interval_to_minute_double(i) + this->dps.front()->get_start_time();
}

bool NetworkHandle::uses_point_queue_model() const
{
    return this->tfm == TrafficFlowModel::point_queue;
}

bool NetworkHandle::uses_spatial_queue_model() const
{
    return this->tfm == TrafficFlowModel::spatial_queue;
}

bool NetworkHandle::uses_kinematic_wave_model() const
{
    return this->tfm == TrafficFlowModel::kinematic_wave;
}

bool NetworkHandle::has_dep_agents(size_type i) const
{
    return this->td_agents.find(i) != this->td_agents.end();
}

void NetworkHandle::setup_agents()
{
    size_type agent_no = 0;
    for (const auto& cv : this->cp.get_column_vecs())
    {
        // oz_no, dz_no, dp_no, at_no
        auto oz_no = std::get<0>(cv.get_key());
        auto dz_no = std::get<1>(cv.get_key());
        auto dp_no = std::get<2>(cv.get_key());
        auto at_no = std::get<3>(cv.get_key());

        auto beg_intvl = this->get_beg_simulation_interval(dp_no);
        auto dp_dur = this->dps[dp_no]->get_duration();
        auto dp_st = this->dps[dp_no]->get_start_time();
        auto dp_intvls = this->cast_minute_to_interval(dp_dur);

        // S2c: profile-consuming vehicleization. When this (period, agent)
        // has a bound conditional distribution (F03c), departures follow the
        // classical quantile inverse-CDF (DTALite get_deparure_time_in_min):
        // r = i/n -> bin s with F(s-1) <= r < F(s) -> within-bin linear
        // interpolation. Deterministic at every n (frozen deviation from
        // classical's RNG small-sample rule). Unbound -> S2b uniform.
        const DepartureProfile* profile = nullptr;
        const auto& at_name = this->ats[at_no]->get_name();
        for (const auto dpr : this->dep_profiles)
        {
            if (dpr->get_period_id() != this->dps[dp_no]->get_period_id())
                continue;

            if (dpr->get_agent_type().empty() || dpr->get_agent_type() == at_name)
            {
                profile = dpr;
                break;
            }
        }

        // S2a: conserved integer vehicleization by largest remainder over the
        // column vector - the sum of agents equals round(sum of column
        // volumes) exactly. The previous per-column ceil inflated counts
        // (defect F-2); classical DTALite rounds (path_volume + 0.5), and
        // largest remainder is the conserved strengthening of that rule.
        // Deterministic: no RNG; ties resolved by container order.
        std::vector<const Column*> cols;
        std::vector<size_type> counts;
        std::vector<double> residuals;
        double vol_sum = 0;
        size_type assigned = 0;
        for (const auto& col : cv.get_columns())
        {
            auto vol = col.get_volume();
            auto n = static_cast<size_type>(std::floor(vol));
            cols.push_back(&col);
            counts.push_back(n);
            residuals.push_back(vol - n);
            vol_sum += vol;
            assigned += n;
        }

        auto target = static_cast<size_type>(vol_sum + 0.5);
        while (assigned < target)
        {
            std::vector<double>::size_type best = 0;
            for (std::vector<double>::size_type c = 1; c != residuals.size(); ++c)
            {
                if (residuals[c] > residuals[best])
                    best = c;
            }

            ++counts[best];
            residuals[best] = -1;
            ++assigned;
        }

        for (std::vector<const Column*>::size_type c = 0; c != cols.size(); ++c)
        {
            const auto col = cols[c];
            for (size_type i = 0, n = counts[c]; i != n; ++i)
            {
                // avoid copy by constructing Agent object in place
                this->agents.emplace_back(agent_no, at_no, dp_no, oz_no, dz_no, col);

                // S2b: departure realization at simulation-interval
                // resolution - uniform over the period by exact integer
                // arithmetic (the previous whole-minute truncation released
                // each minute's demand as one burst: the +18 family).
                // Classical DTALite generates continuous fractional-minute
                // departures via the v/N quantile; interval-uniform placement
                // is that behavior at the engine's native resolution.
                auto intvl = beg_intvl + i * dp_intvls / n;
                auto dep_time = dp_st + static_cast<double>(i) * dp_dur / n;

                if (profile)
                {
                    // S2c: inverse CDF over the conditional bins
                    auto r = static_cast<double>(i) / n;
                    double cum = 0;
                    double offset = 0;
                    for (const auto& b : profile->get_bins())
                    {
                        if (r < cum + b.weight)
                        {
                            offset = b.start_min + (r - cum) / b.weight * b.width_min
                                     - dp_st;
                            break;
                        }

                        cum += b.weight;
                        // numerical tail: place at the end of the last bin
                        offset = b.start_min + b.width_min - dp_st;
                    }

                    intvl = beg_intvl + static_cast<size_type>(
                        offset * SECONDS_IN_MINUTE / this->simu_res);
                    dep_time = dp_st + offset;
                }

                auto& agent = this->get_agent(agent_no);
                agent.set_arr_interval(intvl);
                agent.set_dep_time(dep_time);

                this->td_agents[intvl].push_back(agent_no++);
            }
        }
    }
}

void NetworkHandle::setup_link_queues()
{
    for (const auto link : this->net.get_links())
    {
        link_queues.emplace_back(link, this->get_simulation_intervals(),
                                 this->simu_dur, this->simu_res);
    }
}

void NetworkHandle::run_simulation()
{
    this->setup_agents();
    if (this->td_agents.empty())
        return;

    this->setup_link_queues();
    if (this->link_queues.empty())
        return;

    size_type cum_arr = 0;
    size_type cum_dep = 0;

    unsigned short dp_no = 0;
    size_type ub = this->get_end_simulation_interval(dp_no);
    // number of simulation intervals in one minute
    const unsigned short num = this->cast_minute_to_interval(1);

    for (size_type t = 0, e = this->get_simulation_intervals(); t != e; ++t)
    {
        if (t % num == 0)
            std::cout << "simulation time = " << t / num << " min, CA = "
                      << cum_arr << ", CD = " << cum_dep << '\n';

        if (t >= ub)
        {
            // restrict dp_no as we allow user to add buffer time to simulation
            // in addition to the given demand periods
            if (dp_no < this->dps.size() - 1)
                ub = this->get_end_simulation_interval(++dp_no);
            else
                ub = this->get_simulation_intervals();
        }

        if (t)
        {
            for (auto& link_que : this->link_queues)
                link_que.update_cum_states(t);
        }

        if (this->has_dep_agents(t))
        {
            for (auto a_no : this->get_agents_at_interval(t))
            {
                const auto& agent = this->get_agent(a_no);
                // is this check necessary?
                if (!agent.get_link_num())
                    continue;

                auto& link_que = this->get_link_queue(agent.get_first_link_no());
                link_que.increment_cum_arr(t);
                link_que.append_entr_queue(a_no);
                ++cum_arr;
            }
        }

        for (auto& link_que : this->link_queues)
        {
            while (!link_que.is_entr_queue_empty())
            {
                auto a_no = link_que.get_entr_queue_front();
                link_que.pop_entr_queue_front();

                auto& agent = this->get_agent(a_no);
                auto intvl = link_que.get_period_fftt_intvl(dp_no);

                link_que.append_exit_queue(a_no);
                agent.increment_dep_interval(intvl);
            }
        }

        for (const auto node : this->net.get_nodes())
        {
            for (size_type i = 0, m = node->get_incoming_links().size(); i != m; ++i)
            {
                auto j = (t + i) % m;
                auto link_no = node->get_incoming_links()[j]->get_no();
                auto& link_que = this->get_link_queue(link_no);

                while (link_que.has_outflow_cap(t) && !link_que.is_exit_queue_empty())
                {
                    auto a_no = link_que.get_exit_queue_front();
                    auto& agent = this->get_agent(a_no);

                    if (agent.get_dep_interval() > t)
                        break;

                    if (agent.reaches_last_link())
                    {
                        // S0c-1: record the ACTUAL departure - the earliest
                        // time preset at entrance->exit transfer otherwise
                        // survives and under-reports the terminal-link travel
                        // time by the whole queueing delay
                        agent.set_dep_interval(t);
                        // S0c-2: account waiting on the terminal link exactly
                        // as the transfer branch does (same dp_no semantics;
                        // both call sites migrate to arrival-clock supply
                        // lookup together when mu(t) lands - see mini-spec)
                        link_que.update_waiting_time(t, agent.get_arr_interval(), dp_no);
                        link_que.increment_cum_dep(t);
                        ++cum_dep;
                    }
                    else
                    {
                        auto next_link_no = agent.get_next_link_no();
                        auto& next_link_que = this->get_link_queue(next_link_no);

                        // it will be checked over and over again, which is not efficient!
                        if (this->uses_spatial_queue_model())
                        {
                            // if t = 0, the whole while loop will be skipped as exit queue is empty.
                            auto num = next_link_que.get_waiting_vehicle_num_sq(t - 1);
                            if (num > next_link_que.get_spatial_capacity())
                                break;
                        }
                        else if (this->uses_kinematic_wave_model())
                        {
                            auto num = next_link_que.get_waiting_vehicle_num_kw(t - 1);
                            if (num > next_link_que.get_spatial_capacity())
                                break;
                        }

                        next_link_que.append_entr_queue(a_no);
                        // departure interval for the current link, i.e.,link_que, is t
                        agent.set_dep_interval(t);
                        // arrival interval for the next link, i.e., next_link_que, is t
                        agent.set_arr_interval(t, 1);

                        link_que.update_waiting_time(t, agent.get_arr_interval(), dp_no);
                        link_que.increment_cum_dep(t);
                        next_link_que.increment_cum_arr(t);
                    }

                    agent.move_to_next_link();
                    // remove agent (i.e., a_no) from exit queue
                    link_que.pop_exit_queue_front();
                    link_que.deduct_outflow_cap(t);
                }
            }
        }
    }
}