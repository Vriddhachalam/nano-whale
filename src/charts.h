#pragma once

#include <string>
#include <vector>
#include <deque>
#include <cmath>
#include <sstream>
#include <algorithm>

namespace nw {
namespace charts {

/// Render a braille dot chart from a time series.
/// Returns a multi-line string suitable for terminal display.
///
/// @param data    Time series values.
/// @param height  Number of character rows for the chart area.
/// @param width   Number of character columns for the chart area.
/// @param label   Label text to display below the chart (e.g., "CPU:").
std::string smooth_chart(const std::deque<double>& data,
                         int height = 12, int width = 55,
                         const std::string& label = "");

/// Convert a byte count to a human-readable string (e.g., "1.5MB").
std::string human_bytes(double n);

} // namespace charts
} // namespace nw
