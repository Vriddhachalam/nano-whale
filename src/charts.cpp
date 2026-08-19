#include "charts.h"

#include <iomanip>

namespace nw {
namespace charts {

std::string smooth_chart(const std::deque<double>& data,
                         int height, int width,
                         const std::string& label) {
    std::ostringstream out;

    if (data.size() < 2) {
        // Not enough data — render empty chart
        for (int r = 0; r < height; ++r) {
            out << std::string(width, ' ') << "\n";
        }
        out << "        " << label << " 0.00 % (waiting...)";
        return out.str();
    }

    // Get the tail slice
    int slice_len = std::min(static_cast<int>(data.size()), width);
    std::vector<double> slice(data.end() - slice_len, data.end());

    double max_val = *std::max_element(slice.begin(), slice.end());
    double min_val = *std::min_element(slice.begin(), slice.end());
    double range = max_val - min_val;
    if (range < 0.001) range = 1.0;

    // Braille dot patterns: [row_offset][col_offset]
    // Each braille character encodes a 2x4 pixel cell.
    // The dot positions are:
    //   col0: row0=0x01, row1=0x02, row2=0x04, row3=0x40
    //   col1: row0=0x08, row1=0x10, row2=0x20, row3=0x80
    static const int dots[4][2] = {
        {0x01, 0x08},
        {0x02, 0x10},
        {0x04, 0x20},
        {0x40, 0x80}
    };

    int px_w = width * 2;
    int px_h = height * 4;

    // Create pixel canvas
    std::vector<std::vector<int>> canvas(px_h, std::vector<int>(px_w, 0));

    // Map value to pixel Y coordinate
    auto val_to_y = [&](double v) -> int {
        return static_cast<int>(
            std::round(px_h - 1 - ((v - min_val) / range) * (px_h - 1)));
    };

    // Draw line segments between consecutive data points
    for (int i = 0; i < slice_len - 1; ++i) {
        int x0 = static_cast<int>(std::round(
            static_cast<double>(i) / (slice_len - 1) * (px_w - 1)));
        int x1 = static_cast<int>(std::round(
            static_cast<double>(i + 1) / (slice_len - 1) * (px_w - 1)));
        int y0 = val_to_y(slice[i]);
        int y1 = val_to_y(slice[i + 1]);

        int steps = std::max(std::abs(x1 - x0), std::abs(y1 - y0)) * 2;
        if (steps == 0) steps = 1;

        for (int s = 0; s <= steps; ++s) {
            double t = static_cast<double>(s) / steps;
            int sx = static_cast<int>(std::round(x0 + (x1 - x0) * t));
            int sy = static_cast<int>(std::round(y0 + (y1 - y0) * t));

            // Draw with slight thickness
            for (int dy = 0; dy <= 1; ++dy) {
                for (int dx = 0; dx <= 1; ++dx) {
                    int cx = sx + dx;
                    int cy = sy + dy;
                    if (cx >= 0 && cx < px_w && cy >= 0 && cy < px_h) {
                        canvas[cy][cx] = 1;
                    }
                }
            }
        }
    }

    // Render canvas to braille characters
    for (int row = 0; row < px_h; row += 4) {
        // Y-axis label
        double val = max_val - (static_cast<double>(row) / 4.0 / (height - 1)) * range;
        out << std::setw(6) << std::fixed << std::setprecision(2) << val << " |";

        for (int col = 0; col < px_w; col += 2) {
            int code = 0x2800; // braille blank
            for (int dy = 0; dy < 4; ++dy) {
                for (int dx = 0; dx < 2; ++dx) {
                    int py = row + dy;
                    int px = col + dx;
                    if (py < px_h && px < px_w && canvas[py][px]) {
                        code |= dots[dy][dx];
                    }
                }
            }
            // Encode the braille character as UTF-8
            if (code < 0x80) {
                out << static_cast<char>(code);
            } else if (code < 0x800) {
                out << static_cast<char>(0xC0 | (code >> 6));
                out << static_cast<char>(0x80 | (code & 0x3F));
            } else {
                out << static_cast<char>(0xE0 | (code >> 12));
                out << static_cast<char>(0x80 | ((code >> 6) & 0x3F));
                out << static_cast<char>(0x80 | (code & 0x3F));
            }
        }
        out << "\n";
    }

    // Bottom axis
    out << "       +" << std::string(width, '-') << "\n";

    // Current value
    double cur = slice.back();
    out << "\n        " << label << " " << std::fixed << std::setprecision(2) << cur
        << " %  (" << slice_len * 2 << "s)";

    return out.str();
}

std::string human_bytes(double n) {
    static const char* units[] = {"B", "kB", "MB", "GB", "TB"};
    int i = 0;
    while (n >= 1024.0 && i < 4) {
        n /= 1024.0;
        ++i;
    }
    std::ostringstream out;
    out << std::fixed << std::setprecision(1) << n << units[i];
    return out.str();
}

} // namespace charts
} // namespace nw
