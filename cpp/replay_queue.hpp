#pragma once
#include <array>
#include <cstdint>
#include <tuple>
#include <vector>
namespace rq {
using I = std::int64_t;
using State = std::tuple<int,double,I,I,I,I,I>;
struct Replay {
 std::vector<std::vector<double>> values;
 std::vector<double> snapshots;
 std::vector<std::uint8_t> valid;
 std::vector<I> segment, live, old_priority, new_priority;
 std::vector<State> state;
 explicit Replay(std::size_t n);
};
Replay replay(const I* rows, std::size_t n, I start, I end, bool reset);
struct Paths {
 std::vector<std::vector<double>> values;
 std::vector<I> fill, adverse;
 std::vector<std::uint8_t> first_fill, first_adverse, simultaneous;
 explicit Paths(std::size_t n);
};
Paths paths(const std::array<const double*,16>& e, const std::uint8_t* valid,
 const I* segment, std::size_t n, const I* placement, std::size_t count,
 int side, int horizon, const double* tick, int latency);
}
