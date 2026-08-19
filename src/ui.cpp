#include "ui.h"
#include "charts.h"
#include "docker.h"
#include "platform.h"
#include "ascii_art.h"

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/component/screen_interactive.hpp>
#include <ftxui/dom/elements.hpp>
#include <ftxui/screen/color.hpp>

#include "platform.h"

#include <algorithm>
#include <chrono>
#include <regex>
#include <thread>
#include <sstream>
#include <iomanip>

using namespace ftxui;

namespace nw {
namespace ui {

// ── Helpers ──────────────────────────────────────────────────────────────

static std::string pad_right(const std::string &s, size_t width) {
  if (s.size() >= width)
    return s.substr(0, width);
  return s + std::string(width - s.size(), ' ');
}

static std::string pad_left(const std::string &s, size_t width) {
  if (s.size() >= width)
    return s.substr(0, width);
  return std::string(width - s.size(), ' ') + s;
}

static Color state_color(const std::string &st) {
  if (st == "running")
    return Color::Green;
  if (st == "paused")
    return Color::Yellow;
  return Color::Red;
}

// Container list entry
static Element render_container_entry(const Container &c, const AppState &state,
                                      bool selected) {
  bool marked = state.marked_containers.count(c.name) > 0;
  std::string mark_str = marked ? "[✓] " : "    ";

  std::string status_str;
  Color sc;
  if (c.state == "running") {
    if (c.status.find("healthy") != std::string::npos) {
      status_str = "running (healthy)";
    } else if (c.status.find("Paused") != std::string::npos) {
      status_str = "paused";
      sc = Color::Yellow;
    } else {
      status_str = "running";
    }
    sc = state_color(c.state);
  } else {
    status_str = "exited";
    sc = Color::Red;
  }

  auto it = state.stats.find(c.name);
  double cpu = (it != state.stats.end()) ? it->second.cpu : 0.0;
  std::string cpu_str;
  if (c.is_running()) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(2) << cpu << "%";
    cpu_str = oss.str();
  } else {
    cpu_str = "-";
  }

  std::string ports_str = c.ports.substr(0, 14);

  auto entry = hbox({
      text(mark_str),
      text(pad_right(status_str, 18)) | color(sc),
      text(" "),
      text(pad_right(c.name, 18)) | bold,
      text(" "),
      text(pad_left(cpu_str, 7)),
      text(" "),
      text(ports_str) | color(Color::Cyan),
  });

  if (selected) {
    entry = entry | inverted;
  }

  return entry;
}

// ── Image list entry ─────────────────────────────────────────────────────

static Element render_image_entry(const Image &img, const AppState &state,
                                  bool selected) {
  bool marked = state.marked_images.count(img.id) > 0;
  std::string mark_str = marked ? "[✓] " : "    ";

  auto entry = hbox({
      text(mark_str),
      text(pad_right(img.repo, 20)),
      text(" "),
      text(pad_right(img.tag, 10)) | color(Color::Yellow),
      text(" "),
      text(pad_right(img.size, 10)),
  });

  if (selected)
    entry = entry | inverted;
  return entry;
}

// ── Volume list entry ────────────────────────────────────────────────────

static Element render_volume_entry(const Volume &v, const AppState &state,
                                   bool selected) {
  bool marked = state.marked_volumes.count(v.name) > 0;
  std::string mark_str = marked ? "[✓] " : "    ";

  auto entry = hbox({
      text(mark_str),
      text(pad_right(v.driver, 8)) | color(Color::Magenta),
      text(" "),
      text(v.name),
  });

  if (selected)
    entry = entry | inverted;
  return entry;
}

// ── Network list entry ───────────────────────────────────────────────────

static Element render_network_entry(const Network &n, bool selected) {
  bool is_system = (n.name == "bridge" || n.name == "host" || n.name == "none");

  Element entry;
  if (is_system) {
    entry = hbox({
                text(pad_right(n.driver, 8)),
                text(" "),
                text(n.name + " (system)"),
            }) |
            color(Color::GrayDark);
  } else {
    entry = hbox({
        text(pad_right(n.driver, 8)) | color(Color::Blue),
        text(" "),
        text(n.name),
    });
  }

  if (selected)
    entry = entry | inverted;
  return entry;
}

// ── Tab content renderers ────────────────────────────────────────────────

static Element render_logs_tab(AppState &state) {
  const Container *c = get_selected_container(state);
  if (!c) {
    return text("No container selected") | color(Color::Yellow) | center;
  }

  // Fetch logs if we haven't yet, or refresh
  std::string name = c->name;
  if (state.logs_content.empty()) {
    state.logs_content = docker::get_logs(name, "100");
  }

  if (state.logs_content.empty()) {
    return text("No logs yet...") | color(Color::GrayDark) | center;
  }

  auto lines = platform::split(state.logs_content, '\n');
  Elements log_lines;
  for (const auto &line : lines) {
    log_lines.push_back(text(line));
  }

  return vbox(std::move(log_lines));
}

static Element render_stats_tab(AppState &state) {
  const Container *c = get_selected_container(state);
  if (!c) {
    return text("No container selected") | color(Color::Yellow) | center;
  }

  Elements content;
  content.push_back(hbox({text("Stats: ") | bold | color(Color::Cyan),
                          text(c->name) | bold | color(Color::Cyan)}));
  content.push_back(separator());
  content.push_back(text(""));

  if (!c->is_running()) {
    content.push_back(text("Container is not running") |
                      color(Color::GrayDark));
    content.push_back(text("Press [s] to start") | color(Color::GrayDark));
    return vbox(std::move(content));
  }

  // CPU chart
  auto cpu_it = state.cpu_history.find(c->name);
  if (cpu_it != state.cpu_history.end() && cpu_it->second.size() >= 2) {
    std::string chart = charts::smooth_chart(cpu_it->second, 10, 50, "CPU:   ");
    auto chart_lines = platform::split(chart, '\n');
    for (const auto &line : chart_lines) {
      content.push_back(text(line) | color(Color::Cyan));
    }
  } else {
    content.push_back(text("CPU: waiting for data...") |
                      color(Color::GrayDark));
  }

  content.push_back(text(""));

  // Memory chart
  auto mem_it = state.mem_history.find(c->name);
  if (mem_it != state.mem_history.end() && mem_it->second.size() >= 2) {
    std::string chart = charts::smooth_chart(mem_it->second, 10, 50, "Memory:");
    auto chart_lines = platform::split(chart, '\n');
    for (const auto &line : chart_lines) {
      content.push_back(text(line) | color(Color::Green));
    }
  } else {
    content.push_back(text("Memory: waiting for data...") |
                      color(Color::GrayDark));
  }

  content.push_back(text(""));

  // Additional stats
  auto stats_it = state.stats.find(c->name);
  if (stats_it != state.stats.end()) {
    const auto &st = stats_it->second;
    content.push_back(hbox(
        {text("PIDs:     ") | bold | color(Color::Yellow), text(st.pids)}));
    content.push_back(hbox(
        {text("Net IO:   ") | bold | color(Color::Blue), text(st.net_io)}));
    content.push_back(hbox({text("Block IO: ") | bold | color(Color::Magenta),
                            text(st.block_io)}));
    content.push_back(hbox(
        {text("Mem:      ") | bold | color(Color::Green), text(st.mem_usage)}));
  }

  return vbox(std::move(content));
}

static Element render_env_tab(AppState &state) {
  const Container *c = get_selected_container(state);
  if (!c) {
    return text("No container selected") | color(Color::Yellow) | center;
  }

  // Check cache
  auto it = state.env_cache.find(c->name);
  if (it == state.env_cache.end()) {
    auto env = docker::get_container_env(c->name);
    state.env_cache[c->name] = env;
    it = state.env_cache.find(c->name);
  }

  Elements content;
  content.push_back(
      hbox({text("Environment Variables: ") | bold | color(Color::Cyan),
            text(c->name) | bold | color(Color::Cyan)}));
  content.push_back(separator());
  content.push_back(text(""));

  if (it->second.empty()) {
    content.push_back(text("No environment variables found") |
                      color(Color::Yellow));
  } else {
    for (const auto &env : it->second) {
      auto eq_pos = env.find('=');
      if (eq_pos != std::string::npos) {
        std::string key = env.substr(0, eq_pos);
        std::string val = env.substr(eq_pos + 1);
        content.push_back(hbox({
            text(key) | bold,
            text("="),
            text(val) | color(Color::Green),
        }));
      } else {
        content.push_back(text(env));
      }
    }
  }

  return vbox(std::move(content));
}

static Element render_config_tab(AppState &state) {
  const Container *c = get_selected_container(state);
  if (!c) {
    return text("No container selected") | color(Color::Yellow) | center;
  }

  // Check cache
  auto it = state.config_cache.find(c->name);
  if (it == state.config_cache.end()) {
    auto inspect = docker::get_container_inspect(c->name);
    if (inspect) {
      state.config_cache[c->name] = *inspect;
    } else {
      state.config_cache[c->name] = nlohmann::json();
    }
    it = state.config_cache.find(c->name);
  }

  Elements content;
  content.push_back(hbox({text("Configuration: ") | bold | color(Color::Cyan),
                          text(c->name) | bold | color(Color::Cyan)}));
  content.push_back(separator());
  content.push_back(text(""));

  const auto &j = it->second;
  if (j.is_null() || j.empty()) {
    content.push_back(text("Failed to get container configuration") |
                      color(Color::Red));
    return vbox(std::move(content));
  }

  auto safe_str = [&](const nlohmann::json &obj,
                      const std::string &key) -> std::string {
    if (obj.contains(key) && obj[key].is_string())
      return obj[key].get<std::string>();
    return "N/A";
  };

  // Basic info
  std::string id_str = safe_str(j, "Id");
  if (id_str.size() > 12)
    id_str = id_str.substr(0, 12);
  content.push_back(hbox({text("ID:          ") | bold, text(id_str)}));
  content.push_back(
      hbox({text("Created:     ") | bold, text(safe_str(j, "Created"))}));

  if (j.contains("Config") && j["Config"].is_object()) {
    const auto &cfg = j["Config"];
    content.push_back(
        hbox({text("Image:       ") | bold, text(safe_str(cfg, "Image"))}));

    if (cfg.contains("Entrypoint") && !cfg["Entrypoint"].is_null()) {
      content.push_back(
          hbox({text("Entrypoint:  ") | bold, text(cfg["Entrypoint"].dump())}));
    }
    if (cfg.contains("Cmd") && !cfg["Cmd"].is_null()) {
      content.push_back(
          hbox({text("Cmd:         ") | bold, text(cfg["Cmd"].dump())}));
    }

    std::string wd = safe_str(cfg, "WorkingDir");
    content.push_back(
        hbox({text("WorkingDir:  ") | bold, text(wd.empty() ? "/" : wd)}));
  }

  content.push_back(text(""));

  // Network Settings
  if (j.contains("NetworkSettings") && j["NetworkSettings"].is_object()) {
    const auto &ns = j["NetworkSettings"];

    content.push_back(text("Network Settings:") | bold | color(Color::Yellow));
    if (ns.contains("Networks") && ns["Networks"].is_object()) {
      for (auto &[net_name, net_cfg] : ns["Networks"].items()) {
        content.push_back(hbox({text("  "), text(net_name + ":") | bold}));
        content.push_back(hbox(
            {text("    IP:      "), text(safe_str(net_cfg, "IPAddress"))}));
        content.push_back(
            hbox({text("    Gateway: "), text(safe_str(net_cfg, "Gateway"))}));
        content.push_back(hbox(
            {text("    MAC:     "), text(safe_str(net_cfg, "MacAddress"))}));
      }
    }

    content.push_back(text(""));

    content.push_back(text("Port Bindings:") | bold | color(Color::Green));
    if (ns.contains("Ports") && ns["Ports"].is_object()) {
      bool has_ports = false;
      for (auto &[port, bindings] : ns["Ports"].items()) {
        if (bindings.is_array()) {
          for (const auto &b : bindings) {
            std::string host_ip = safe_str(b, "HostIp");
            std::string host_port = safe_str(b, "HostPort");
            if (host_ip.empty())
              host_ip = "0.0.0.0";
            content.push_back(hbox({
                text("  "),
                text(host_ip + ":" + host_port) | color(Color::Cyan),
                text(" -> "),
                text(port),
            }));
            has_ports = true;
          }
        } else {
          content.push_back(hbox({text("  "), text(port + " (not bound)")}));
          has_ports = true;
        }
      }
      if (!has_ports) {
        content.push_back(text("  No ports exposed") | color(Color::GrayDark));
      }
    }
  }

  content.push_back(text(""));

  // Mounts
  content.push_back(text("Mounts:") | bold | color(Color::Magenta));
  if (j.contains("Mounts") && j["Mounts"].is_array()) {
    if (j["Mounts"].empty()) {
      content.push_back(text("  No mounts") | color(Color::GrayDark));
    } else {
      for (const auto &mount : j["Mounts"]) {
        std::string type = safe_str(mount, "Type");
        std::string source = safe_str(mount, "Source");
        std::string dest = safe_str(mount, "Destination");
        content.push_back(hbox({text("  "), text(type + ": " + source)}));
        content.push_back(hbox({text("    -> "), text(dest)}));
      }
    }
  }

  content.push_back(text(""));

  // Resource Limits
  content.push_back(text("Resource Limits:") | bold | color(Color::Red));
  if (j.contains("HostConfig") && j["HostConfig"].is_object()) {
    const auto &hc = j["HostConfig"];

    std::string cpu_shares = "default";
    if (hc.contains("CpuShares") && hc["CpuShares"].is_number()) {
      int shares = hc["CpuShares"].get<int>();
      if (shares > 0)
        cpu_shares = std::to_string(shares);
    }
    content.push_back(hbox({text("  CPU Shares:      "), text(cpu_shares)}));

    std::string mem_limit = "unlimited";
    if (hc.contains("Memory") && hc["Memory"].is_number()) {
      long long mem = hc["Memory"].get<long long>();
      if (mem > 0) {
        mem_limit = std::to_string(mem / 1024 / 1024) + "MB";
      }
    }
    content.push_back(hbox({text("  Memory Limit:    "), text(mem_limit)}));

    std::string restart = "no";
    if (hc.contains("RestartPolicy") && hc["RestartPolicy"].is_object()) {
      restart = safe_str(hc["RestartPolicy"], "Name");
      if (restart.empty())
        restart = "no";
    }
    content.push_back(hbox({text("  Restart Policy:  "), text(restart)}));
  }

  return vbox(std::move(content));
}

static Element render_top_tab(AppState &state) {
  const Container *c = get_selected_container(state);
  if (!c) {
    return text("No container selected") | color(Color::Yellow) | center;
  }

  Elements content;
  content.push_back(hbox({text("Top Processes: ") | bold | color(Color::Cyan),
                          text(c->name) | bold | color(Color::Cyan)}));
  content.push_back(separator());
  content.push_back(text(""));

  if (!c->is_running()) {
    content.push_back(text("Container is not running") |
                      color(Color::GrayDark));
    return vbox(std::move(content));
  }

  // Check cache
  auto it = state.top_cache.find(c->name);
  if (it == state.top_cache.end()) {
    auto top_info = docker::get_container_top(c->name);
    state.top_cache[c->name] = top_info;
    it = state.top_cache.find(c->name);
  }

  auto lines = platform::split(it->second, '\n');
  for (const auto &line : lines) {
    content.push_back(text(line) | color(Color::Green));
  }

  return vbox(std::move(content));
}

static Element render_compose_tab(AppState &state) {
  if (!state.compose_available) {
    return text("No docker-compose.yml found in current directory.") | color(Color::Yellow) | center;
  }
  
  Elements content;
  content.push_back(text(" Docker Compose Project Found! ") | bold | color(Color::Green));
  content.push_back(text(""));
  content.push_back(hbox({
    text("[u] Up (-d)") | bold | color(Color::Green), text("   |   "),
    text("[d] Down") | bold | color(Color::Red)
  }));
  
  content.push_back(separator());
  
  if (state.compose_logs.empty()) {
    content.push_back(text("No logs available or project is down."));
  } else {
    auto lines = platform::split(state.compose_logs, '\n');
    for (const auto& line : lines) {
      content.push_back(text(line));
    }
  }
  return vbox(std::move(content));
}

static Element render_about_tab(AppState &state) {
  Elements content;
  content.push_back(text(""));
  content.push_back(text(" Nano Whale ") | bold | color(Color::Cyan) | center);
  content.push_back(text(" The blazing-fast C++ Docker TUI ") | dim | center);
  content.push_back(text(""));
  content.push_back(render_ascii_art() | center);
  content.push_back(text(""));
  
  return vbox(std::move(content)) | center;
}

// ── Main UI ──────────────────────────────────────────────────────────────

void run(AppState &state) {
  auto screen = ScreenInteractive::Fullscreen();

  // We use a CatchEvent + Renderer approach for the full layout.

  // ── Notification timer ───────────────────────────────────────────────
  auto notification_time = std::chrono::steady_clock::now();

  auto set_notification = [&](const std::string &msg,
                              const std::string &col = "green") {
    state.notification = msg;
    state.notification_color = col;
    notification_time = std::chrono::steady_clock::now();
  };

  // ── Pending confirm action ───────────────────────────────────────────
  std::function<void()> confirm_action;

  // ── Build the component ──────────────────────────────────────────────
  auto component = Renderer([&] {
    std::lock_guard<std::mutex> lock(state.mtx);
    auto now = std::chrono::steady_clock::now();

    // Clear notification after 2 seconds
    if (!state.notification.empty()) {
      auto since_notify = std::chrono::duration_cast<std::chrono::seconds>(
                              now - notification_time)
                              .count();
      if (since_notify >= 2) {
        state.notification.clear();
      }
    }

    // ── Left Panel ──────────────────────────────────────────────────

    // Device box
    auto device_box = window(text(" [1]-Device ") | color(Color::Cyan),
                             text(platform::get_hostname())) |
                      size(HEIGHT, EQUAL, 3);

    // Containers list
    Elements container_entries;
    if (state.containers.empty()) {
      container_entries.push_back(text("No containers") | color(Color::Yellow));
    } else {
      for (int i = 0; i < static_cast<int>(state.containers.size()); ++i) {
        container_entries.push_back(render_container_entry(
            state.containers[i], state,
            i == state.selected_container &&
                state.focused_list == FocusedList::Containers));
      }
    }
    auto containers_box = window(text(" [2]-Containers ") | color(Color::Green),
                                 vbox(std::move(container_entries)) |
                                     vscroll_indicator | yframe) |
                          flex;

    // Images list
    Elements image_entries;
    if (state.images.empty()) {
      image_entries.push_back(text("No images") | color(Color::Yellow));
    } else {
      for (int i = 0; i < static_cast<int>(state.images.size()); ++i) {
        image_entries.push_back(
            render_image_entry(state.images[i], state,
                               i == state.selected_image &&
                                   state.focused_list == FocusedList::Images));
      }
    }
    auto images_box =
        window(text(" [3]-Images ") | color(Color::Yellow),
               vbox(std::move(image_entries)) | vscroll_indicator | yframe) |
        flex;

    // Volumes list
    Elements volume_entries;
    if (state.volumes.empty()) {
      volume_entries.push_back(text("No volumes") | color(Color::Yellow));
    } else {
      for (int i = 0; i < static_cast<int>(state.volumes.size()); ++i) {
        volume_entries.push_back(render_volume_entry(
            state.volumes[i], state,
            i == state.selected_volume &&
                state.focused_list == FocusedList::Volumes));
      }
    }
    auto volumes_box =
        window(text(" [4]-Volumes ") | color(Color::Magenta),
               vbox(std::move(volume_entries)) | vscroll_indicator | yframe) |
        flex;

    // Networks list
    Elements network_entries;
    if (state.networks.empty()) {
      network_entries.push_back(text("No networks") | color(Color::Yellow));
    } else {
      for (int i = 0; i < static_cast<int>(state.networks.size()); ++i) {
        network_entries.push_back(render_network_entry(
            state.networks[i],
            i == state.selected_network &&
                state.focused_list == FocusedList::Networks));
      }
    }
    auto networks_box =
        window(text(" [5]-Networks ") | color(Color::Blue),
               vbox(std::move(network_entries)) | vscroll_indicator | yframe) |
        flex;

    auto left_panel = vbox({
        device_box,
        containers_box,
        images_box,
        volumes_box,
        networks_box,
    });

    // ── Right Panel ─────────────────────────────────────────────────

    // Tab header
    Elements tab_elements;
    for (int i = 0; i < TAB_COUNT; ++i) {
      if (i == static_cast<int>(state.current_tab)) {
        tab_elements.push_back(text(std::string(" ") + TAB_NAMES[i] + " ") |
                               bold | color(Color::Cyan));
      } else {
        tab_elements.push_back(text(std::string(" ") + TAB_NAMES[i] + " ") |
                               color(Color::GrayDark));
      }
      if (i < TAB_COUNT - 1) {
        tab_elements.push_back(text("-") | color(Color::White));
      }
    }
    auto tab_header = window(text(""), hbox(std::move(tab_elements))) |
                      size(HEIGHT, EQUAL, 3);

    // Tab content
    Element tab_content;
    switch (state.current_tab) {
    case Tab::Logs:
      tab_content = render_logs_tab(state);
      break;
    case Tab::Stats:
      tab_content = render_stats_tab(state);
      break;
    case Tab::Env:
      tab_content = render_env_tab(state);
      break;
    case Tab::Config:
      tab_content = render_config_tab(state);
      break;
    case Tab::Top:
      tab_content = render_top_tab(state);
      break;
    case Tab::Compose:
      tab_content = render_compose_tab(state);
      break;
    case Tab::About:
      tab_content = render_about_tab(state);
      break;
    }

    auto content_box = window(text("") | color(Color::Cyan),
                              tab_content | vscroll_indicator | yframe) |
                       flex;

    auto right_panel = vbox({
        tab_header,
        content_box,
    });

    // ── Main layout ─────────────────────────────────────────────────

    auto main_layout = hbox({
        left_panel | size(WIDTH, EQUAL, 60),
        right_panel | flex,
    });

    // ── Help bar ────────────────────────────────────────────────────

    auto help = hbox({
                    text("q") | bold,  text(":Quit "),       text("←→") | bold,
                    text(":Tabs "),    text("↑↓") | bold,    text(":Nav "),
                    text("s") | bold,  text(":Start/Stop "), text("r") | bold,
                    text(":Restart "), text("t") | bold,     text(":Exec "),
                    text("d") | bold,  text(":Delete "),     text("m") | bold,
                    text(":Mark "),    text("l") | bold,     text(":Logs "),
                    text("F5") | bold, text(":Refresh "),    text("?") | bold,
                    text(":Help"),
                }) |
                color(Color::White) | bgcolor(Color::Blue);

    // ── Notification overlay ────────────────────────────────────────

    Element overlay = text("");
    if (!state.notification.empty()) {
      Color nc = Color::Green;
      if (state.notification_color == "red")
        nc = Color::Red;
      else if (state.notification_color == "yellow")
        nc = Color::Yellow;
      else if (state.notification_color == "blue")
        nc = Color::Blue;
      else if (state.notification_color == "magenta")
        nc = Color::Magenta;

      overlay =
          text(" " + state.notification + " ") | bold | color(nc) | border;
    }

    // ── Help overlay ──────────────────────────────────────────────────
    if (state.show_help) {
      auto help_content = vbox({
        text(" Keyboard Shortcuts ") | bold | center,
        separator(),
        text(" Navigation ") | bold | color(Color::Cyan),
        text(" ← / →   : Switch Tabs (Containers/Images/Volumes/Networks)"),
        text(" ↑ / ↓   : Navigate lists"),
        text(" Tab     : Switch focus between panels"),
        text(""),
        text(" Container Actions ") | bold | color(Color::Cyan),
        text(" s       : Start / Stop container"),
        text(" r       : Restart container"),
        text(" d       : Delete container / image / volume"),
        text(" m       : Mark/Unmark item for batch operations"),
        text(" t       : Exec into container (opens new terminal)"),
        text(" l       : View fullscreen logs"),
        text(" o / w   : Quick Open web port in browser"),
        text(" i       : Deep Inspect container details"),
        text(" e       : Container File Explorer (Browse & Download)"),
        text(""),
        text(" Global Actions ") | bold | color(Color::Cyan),
        text(" p       : System Prune (Clear unused data)"),
        text(" F5      : Force refresh all data"),
        text(" a       : Toggle auto-scroll in logs"),
        text(" q       : Quit"),
        separator(),
        text(" Press any key to close ") | dim | center
      });
      auto dialog = window(text(" Help "), help_content) |
                    border | bgcolor(Color::Black) | center;

      return vbox({
          dbox({
              main_layout,
              dialog | center | clear_under,
          }) | flex,
          help | size(HEIGHT, EQUAL, 1),
      });
    }

    // ── File Explorer overlay ─────────────────────────────────────────
    if (state.file_explorer.show) {
      Elements file_elements;
      file_elements.push_back(text(" Path: " + state.file_explorer.current_path + " ") | bold | color(Color::Yellow));
      file_elements.push_back(separator());
      
      if (state.file_explorer.files.empty()) {
        file_elements.push_back(text(" Directory is empty or inaccessible ") | color(Color::GrayDark));
      } else {
        for (int i = 0; i < (int)state.file_explorer.files.size(); ++i) {
          const auto& f = state.file_explorer.files[i];
          bool is_selected = (i == state.file_explorer.selected);
          
          Element row = hbox({
            text(f.permissions) | size(WIDTH, EQUAL, 11),
            text(f.size) | size(WIDTH, EQUAL, 6),
            text(f.date) | size(WIDTH, EQUAL, 13),
            text(" " + f.name) | (f.is_dir ? color(Color::Cyan) : color(Color::White))
          });
          
          if (is_selected) row = row | inverted | bold;
          file_elements.push_back(row);
        }
      }
      
      file_elements.push_back(separator());
      file_elements.push_back(hbox({
        text(" [Enter] Open Dir  [d] Download File  [Esc] Close ") | dim | center
      }));
      
      auto dialog = window(text(" File Explorer: " + state.file_explorer.container + " "),
                           vbox(std::move(file_elements)) | vscroll_indicator | yframe | size(HEIGHT, LESS_THAN, 30)) |
                    border | bgcolor(Color::Black) | center;

      return vbox({
          dbox({
              main_layout,
              dialog | center | clear_under,
          }) | flex,
          help | size(HEIGHT, EQUAL, 1),
      });
    }

    // ── Inspect overlay ──────────────────────────────────────────────
    if (state.show_inspect) {
      Elements lines;
      auto raw_lines = platform::split(state.inspect_content, '\n');
      for (const auto& l : raw_lines) {
        lines.push_back(text(l));
      }
      auto dialog = window(text(" Inspect Container ") | bold,
                           vbox(std::move(lines)) | vscroll_indicator | yframe | size(HEIGHT, LESS_THAN, 30)) |
                    border | bgcolor(Color::Black) | center;

      return vbox({
          dbox({
              main_layout,
              dialog | center | clear_under,
          }) | flex,
          help | size(HEIGHT, EQUAL, 1),
      });
    }

    // ── Confirm dialog overlay ──────────────────────────────────────

    if (state.show_confirm) {
      auto dialog = vbox({
                        text(state.confirm_message) | bold | center,
                        text(""),
                        hbox({
                            text("  [y] Yes  ") | color(Color::Green),
                            text("  [n] No   ") | color(Color::Red),
                        }) | center,
                    }) |
                    border | color(Color::Red) | bgcolor(Color::Black) | center;

      return vbox({
          dbox({
              main_layout,
              dialog | center | clear_under,
          }) | flex,
          help | size(HEIGHT, EQUAL, 1),
      });
    }

    // ── Docker not available ────────────────────────────────────────

    if (!state.docker_available) {
      auto error_msg =
          vbox({
              text("Docker not accessible") | color(Color::Red) | bold | center,
              text(""),
              text("Make sure Docker is running.") | center,
          }) |
          border | center;

      return vbox({
          dbox({main_layout, error_msg | center | clear_under}) | flex,
          help | size(HEIGHT, EQUAL, 1),
      });
    }

    // ── Compose final layout ────────────────────────────────────────

    if (!state.notification.empty()) {
      return vbox({
          dbox({
              main_layout,
              overlay | center | clear_under,
          }) | flex,
          help | size(HEIGHT, EQUAL, 1),
      });
    }

    return vbox({
        main_layout | flex,
        help | size(HEIGHT, EQUAL, 1),
    });
  });

  // ── Event Handler ────────────────────────────────────────────────────

  component = CatchEvent(component, [&](Event event) -> bool {
    // Handle help dialog
    if (state.show_help) {
      if (event != Event::Custom) {
        state.show_help = false;
      }
      return true;
    }

    // Handle File Explorer
    if (state.file_explorer.show) {
      if (event == Event::Escape || event == Event::Character('q')) {
        state.file_explorer.show = false;
        return true;
      }
      if (event == Event::ArrowUp) {
        if (state.file_explorer.selected > 0) state.file_explorer.selected--;
        return true;
      }
      if (event == Event::ArrowDown) {
        if (state.file_explorer.selected < (int)state.file_explorer.files.size() - 1) state.file_explorer.selected++;
        return true;
      }
      if (event == Event::Return) {
        if (!state.file_explorer.files.empty()) {
          const auto& f = state.file_explorer.files[state.file_explorer.selected];
          if (f.is_dir) {
            std::string new_path = state.file_explorer.current_path;
            if (f.name == ".") {
              // do nothing
            } else if (f.name == "..") {
              if (new_path != "/") {
                size_t pos = new_path.find_last_of('/');
                if (pos == 0) new_path = "/";
                else if (pos != std::string::npos) new_path = new_path.substr(0, pos);
              }
            } else {
              if (new_path.back() != '/') new_path += "/";
              new_path += f.name;
            }
            state.file_explorer.current_path = new_path;
            state.file_explorer.files = docker::list_files(state.file_explorer.container, new_path);
            state.file_explorer.selected = 0;
          }
        }
        return true;
      }
      if (event == Event::Character('d')) {
        if (!state.file_explorer.files.empty()) {
          const auto& f = state.file_explorer.files[state.file_explorer.selected];
          if (!f.is_dir) {
            std::string full_path = state.file_explorer.current_path;
            if (full_path.back() != '/') full_path += "/";
            full_path += f.name;
            docker::download_file(state.file_explorer.container, full_path);
            set_notification("Downloaded " + f.name, "green");
          } else {
            set_notification("Cannot download a directory", "red");
          }
        }
        return true;
      }
      // Block other events
      if (event.is_character() || event.is_mouse()) return true;
    }

    // Handle inspect dialog
    if (state.show_inspect) {
      if (event == Event::Escape || event == Event::Character('q') || event == Event::Character('i')) {
        state.show_inspect = false;
        return true;
      }
      // Allow scrolling in inspect? We just block other keys
      if (event == Event::ArrowUp || event == Event::ArrowDown) return false;
      return true;
    }

    // Handle confirm dialog
    if (state.show_confirm) {
      if (event == Event::Character('y') || event == Event::Character('Y')) {
        state.show_confirm = false;
        if (confirm_action)
          confirm_action();
        return true;
      }
      if (event == Event::Character('n') || event == Event::Character('N') ||
          event == Event::Escape) {
        state.show_confirm = false;
        return true;
      }
      return true; // Block all other input during confirm
    }

    // Quit
    if (event == Event::Character('q') || event == Event::Special({3})) {
      state.running = false;
      screen.Exit();
      return true;
    }

    // Help
    if (event == Event::Character('?')) {
      state.show_help = true;
      return true;
    }

    // Compose Up/Down
    if (state.current_tab == Tab::Compose && state.compose_available) {
      if (event == Event::Character('u')) {
        state.show_confirm = true;
        state.confirm_message = "Run docker compose up -d?";
        confirm_action = [&] {
          set_notification("Starting compose...", "yellow");
          docker::compose_up();
          refresh_all(state);
          set_notification("Compose started", "green");
        };
        return true;
      }
      if (event == Event::Character('d')) {
        state.show_confirm = true;
        state.confirm_message = "Run docker compose down?";
        confirm_action = [&] {
          set_notification("Stopping compose...", "yellow");
          docker::compose_down();
          refresh_all(state);
          set_notification("Compose stopped", "red");
        };
        return true;
      }
    }

    // Tab switching
    if (event == Event::ArrowRight) {
      int t = static_cast<int>(state.current_tab);
      state.current_tab = static_cast<Tab>((t + 1) % TAB_COUNT);
      // Clear logs cache when switching tabs
      if (state.current_tab == Tab::Logs) {
        const Container *c = get_selected_container(state);
        if (c)
          state.logs_content = docker::get_logs(c->name, "100");
      }
      return true;
    }
    if (event == Event::ArrowLeft) {
      int t = static_cast<int>(state.current_tab);
      state.current_tab = static_cast<Tab>((t - 1 + TAB_COUNT) % TAB_COUNT);
      if (state.current_tab == Tab::Logs) {
        const Container *c = get_selected_container(state);
        if (c)
          state.logs_content = docker::get_logs(c->name, "100");
      }
      return true;
    }

    // Navigate: up/down in focused list
    if (event == Event::ArrowUp) {
      switch (state.focused_list) {
      case FocusedList::Containers:
        if (state.selected_container > 0) {
          state.selected_container--;
          // Clear caches for new selection
          state.env_cache.clear();
          state.config_cache.clear();
          state.top_cache.clear();
          state.logs_content.clear();
        }
        break;
      case FocusedList::Images:
        if (state.selected_image > 0)
          state.selected_image--;
        break;
      case FocusedList::Volumes:
        if (state.selected_volume > 0)
          state.selected_volume--;
        break;
      case FocusedList::Networks:
        if (state.selected_network > 0)
          state.selected_network--;
        break;
      }
      return true;
    }
    if (event == Event::ArrowDown) {
      switch (state.focused_list) {
      case FocusedList::Containers:
        if (state.selected_container <
            static_cast<int>(state.containers.size()) - 1) {
          state.selected_container++;
          state.env_cache.clear();
          state.config_cache.clear();
          state.top_cache.clear();
          state.logs_content.clear();
        }
        break;
      case FocusedList::Images:
        if (state.selected_image < static_cast<int>(state.images.size()) - 1)
          state.selected_image++;
        break;
      case FocusedList::Volumes:
        if (state.selected_volume < static_cast<int>(state.volumes.size()) - 1)
          state.selected_volume++;
        break;
      case FocusedList::Networks:
        if (state.selected_network <
            static_cast<int>(state.networks.size()) - 1)
          state.selected_network++;
        break;
      }
      return true;
    }

    // Tab key: cycle focus between left panels
    if (event == Event::Tab) {
      int f = static_cast<int>(state.focused_list);
      state.focused_list = static_cast<FocusedList>((f + 1) % 4);
      return true;
    }

    // Number keys to focus panels
    if (event == Event::Character('2')) {
      state.focused_list = FocusedList::Containers;
      return true;
    }
    if (event == Event::Character('3')) {
      state.focused_list = FocusedList::Images;
      return true;
    }
    if (event == Event::Character('4')) {
      state.focused_list = FocusedList::Volumes;
      return true;
    }
    if (event == Event::Character('5')) {
      state.focused_list = FocusedList::Networks;
      return true;
    }

    // F5: Refresh all
    if (event == Event::F5) {
      refresh_all(state);
      state.logs_content.clear();
      set_notification("Refreshed all data", "green");
      return true;
    }

    // Mark/unmark
    if (event == Event::Character('m')) {
      switch (state.focused_list) {
      case FocusedList::Containers: {
        const Container *c = get_selected_container(state);
        if (c) {
          if (state.marked_containers.count(c->name))
            state.marked_containers.erase(c->name);
          else
            state.marked_containers.insert(c->name);
        }
        break;
      }
      case FocusedList::Images: {
        if (!state.images.empty()) {
          const auto &img = state.images[state.selected_image];
          if (state.marked_images.count(img.id))
            state.marked_images.erase(img.id);
          else
            state.marked_images.insert(img.id);
        }
        break;
      }
      case FocusedList::Volumes: {
        if (!state.volumes.empty()) {
          const auto &vol = state.volumes[state.selected_volume];
          if (state.marked_volumes.count(vol.name))
            state.marked_volumes.erase(vol.name);
          else
            state.marked_volumes.insert(vol.name);
        }
        break;
      }
      default:
        break;
      }
      return true;
    }

    // Start/Stop container
    if (event == Event::Character('s')) {
      if (state.focused_list != FocusedList::Containers)
        return false;

      if (!state.marked_containers.empty()) {
        // Batch operation
        for (const auto &name : state.marked_containers) {
          auto it =
              std::find_if(state.containers.begin(), state.containers.end(),
                           [&](const Container &c) { return c.name == name; });
          if (it != state.containers.end()) {
            if (it->is_running())
              docker::stop_container(name);
            else
              docker::start_container(name);
          }
        }
        state.marked_containers.clear();
        set_notification("Batch start/stop completed", "green");
      } else {
        const Container *c = get_selected_container(state);
        if (c) {
          if (c->is_running()) {
            docker::stop_container(c->name);
            set_notification("Stopped " + c->name, "yellow");
          } else {
            docker::start_container(c->name);
            set_notification("Started " + c->name, "green");
          }
        }
      }
      refresh_all(state);
      return true;
    }

    // Quick Open in Browser
    if (event == Event::Character('o') || event == Event::Character('w')) {
      if (state.focused_list != FocusedList::Containers)
        return false;

      const Container *c = get_selected_container(state);
      if (c && c->is_running() && !c->ports.empty()) {
        std::regex port_regex(R"(:(\d+)->)");
        std::smatch match;
        if (std::regex_search(c->ports, match, port_regex)) {
          std::string port = match[1].str();
          platform::open_url("http://localhost:" + port);
          set_notification("Opened port " + port, "green");
        } else {
          set_notification("No exposed web port found", "red");
        }
      }
      return true;
    }

    // System Prune
    if (event == Event::Character('p') || event == Event::Character('C')) {
      state.show_confirm = true;
      state.confirm_message = "Run system prune? This removes ALL unused data!";
      confirm_action = [&] {
        docker::system_prune();
        refresh_all(state);
        set_notification("System pruned", "green");
      };
      return true;
    }

    // Deep Inspector
    if (event == Event::Character('i')) {
      if (state.focused_list != FocusedList::Containers)
        return false;
      const Container *c = get_selected_container(state);
      if (c) {
        state.inspect_content = docker::inspect_container(c->name);
        state.show_inspect = true;
      }
      return true;
    }

    // File Explorer
    if (event == Event::Character('e')) {
      if (state.focused_list != FocusedList::Containers)
        return false;
      const Container *c = get_selected_container(state);
      if (c && c->is_running()) {
        state.file_explorer.container = c->name;
        state.file_explorer.current_path = "/";
        state.file_explorer.files = docker::list_files(c->name, "/");
        state.file_explorer.selected = 0;
        state.file_explorer.show = true;
      } else {
        set_notification("Container must be running", "red");
      }
      return true;
    }

    // Restart
    if (event == Event::Character('r')) {
      if (state.focused_list != FocusedList::Containers)
        return false;

      if (!state.marked_containers.empty()) {
        int count = 0;
        for (const auto &name : state.marked_containers) {
          auto it =
              std::find_if(state.containers.begin(), state.containers.end(),
                           [&](const Container &c) {
                             return c.name == name && c.is_running();
                           });
          if (it != state.containers.end()) {
            docker::restart_container(name);
            ++count;
          }
        }
        state.marked_containers.clear();
        set_notification("Restarted " + std::to_string(count) + " container(s)",
                         "blue");
      } else {
        const Container *c = get_selected_container(state);
        if (c && c->is_running()) {
          docker::restart_container(c->name);
          set_notification("Restarted " + c->name, "green");
        }
      }
      refresh_all(state);
      return true;
    }

    // Delete
    if (event == Event::Character('d')) {
      switch (state.focused_list) {
      case FocusedList::Containers: {
        if (!state.marked_containers.empty()) {
          state.show_confirm = true;
          state.confirm_message =
              "Delete " + std::to_string(state.marked_containers.size()) +
              " container(s)?";
          confirm_action = [&] {
            for (const auto &name : state.marked_containers) {
              docker::delete_container(name);
            }
            state.marked_containers.clear();
            refresh_all(state);
            set_notification("Deleted containers", "red");
          };
        } else {
          const Container *c = get_selected_container(state);
          if (c) {
            state.show_confirm = true;
            state.confirm_message = "Delete container " + c->name + "?";
            std::string cname = c->name;
            confirm_action = [&, cname] {
              docker::delete_container(cname);
              refresh_all(state);
              set_notification("Deleted " + cname, "red");
            };
          }
        }
        break;
      }
      case FocusedList::Images: {
        if (!state.marked_images.empty()) {
          state.show_confirm = true;
          state.confirm_message = "Delete " +
                                  std::to_string(state.marked_images.size()) +
                                  " image(s)?";
          confirm_action = [&] {
            for (const auto &id : state.marked_images) {
              docker::delete_image(id);
            }
            state.marked_images.clear();
            refresh_all(state);
            set_notification("Deleted images", "red");
          };
        } else if (!state.images.empty()) {
          const auto &img = state.images[state.selected_image];
          state.show_confirm = true;
          state.confirm_message =
              "Delete image " + img.repo + ":" + img.tag + "?";
          std::string id = img.id;
          confirm_action = [&, id] {
            docker::delete_image(id);
            refresh_all(state);
            set_notification("Deleted image", "yellow");
          };
        }
        break;
      }
      case FocusedList::Volumes: {
        if (!state.marked_volumes.empty()) {
          state.show_confirm = true;
          state.confirm_message = "Delete " +
                                  std::to_string(state.marked_volumes.size()) +
                                  " volume(s)?";
          confirm_action = [&] {
            for (const auto &name : state.marked_volumes) {
              docker::delete_volume(name);
            }
            state.marked_volumes.clear();
            refresh_all(state);
            set_notification("Deleted volumes", "magenta");
          };
        } else if (!state.volumes.empty()) {
          const auto &vol = state.volumes[state.selected_volume];
          state.show_confirm = true;
          state.confirm_message = "Delete volume " + vol.name + "?";
          std::string vname = vol.name;
          confirm_action = [&, vname] {
            docker::delete_volume(vname);
            refresh_all(state);
            set_notification("Deleted volume", "magenta");
          };
        }
        break;
      }
      case FocusedList::Networks: {
        if (!state.networks.empty()) {
          const auto &net = state.networks[state.selected_network];
          if (net.name == "bridge" || net.name == "host" ||
              net.name == "none") {
            set_notification(
                "Cannot delete '" + net.name + "' - system network", "yellow");
          } else {
            state.show_confirm = true;
            state.confirm_message = "Delete network " + net.name + "?";
            std::string nname = net.name;
            confirm_action = [&, nname] {
              docker::delete_network(nname);
              refresh_all(state);
              set_notification("Deleted network", "yellow");
            };
          }
        }
        break;
      }
      }
      return true;
    }

    // Exec into container
    if (event == Event::Character('t')) {
      if (state.focused_list != FocusedList::Containers)
        return false;
      const Container *c = get_selected_container(state);
      if (!c || !c->is_running()) {
        set_notification("Container must be running", "red");
        return true;
      }

      // Shell out to docker exec
      std::string docker_cmd = platform::get_docker_cmd();
      std::string cmd = docker_cmd + " exec -it " + c->name +
                        " sh -c \"exec /bin/bash || exec /bin/sh\"";

      screen.Exit();
      // Note: For exec, we'd need to temporarily exit the TUI.
      // FTXUI doesn't support WithRestoredIO on all platforms.
      // The user can use Ctrl+T to open a new terminal window instead.
      set_notification("Use Ctrl+T to exec in a new terminal window", "yellow");

      refresh_all(state);
      return true;
    }

    // Fullscreen logs
    if (event == Event::Character('l')) {
      if (state.focused_list != FocusedList::Containers)
        return false;
      const Container *c = get_selected_container(state);
      if (!c || !c->is_running()) {
        set_notification("Container must be running", "red");
        return true;
      }

      std::string docker_cmd = platform::get_docker_cmd();
      std::string cmd = docker_cmd + " logs -f " + c->name;

      // Switch to logs tab and refresh
      state.current_tab = Tab::Logs;
      state.logs_content = docker::get_logs(c->name, "500");
      set_notification("Loaded logs for " + c->name, "green");

      return true;
    }

    // New terminal window for exec (Ctrl+T)
    if (event == Event::Special({20})) { // Ctrl+T
      if (state.focused_list != FocusedList::Containers)
        return false;
      const Container *c = get_selected_container(state);
      if (!c || !c->is_running()) {
        set_notification("Container must be running", "red");
        return true;
      }
      std::string cmd = platform::get_docker_cmd() + " exec -it " + c->name +
                        " sh -c \"exec /bin/bash || exec /bin/sh\"";
      platform::spawn_new_window(cmd, "exec-" + c->name);
      set_notification("Opened new terminal window", "green");
      return true;
    }

    // New terminal window for logs (Ctrl+L)
    if (event == Event::Special({12})) { // Ctrl+L
      if (state.focused_list != FocusedList::Containers)
        return false;
      const Container *c = get_selected_container(state);
      if (!c || !c->is_running()) {
        set_notification("Container must be running", "red");
        return true;
      }
      std::string cmd = platform::get_docker_cmd() + " logs -f " + c->name;
      platform::spawn_new_window(cmd, "logs-" + c->name);
      set_notification("Opened new terminal window", "green");
      return true;
    }

    // Auto-scroll toggle
    if (event == Event::Character('a')) {
      state.logs_auto_scroll = !state.logs_auto_scroll;
      set_notification("Auto-scroll: " +
                           std::string(state.logs_auto_scroll ? "ON" : "OFF"),
                       state.logs_auto_scroll ? "green" : "yellow");
      return true;
    }

    return false;
  });

  // Run the screen with a 500ms loop for auto-refresh and background data fetching
  std::thread refresh_thread([&] {
    auto last_container_refresh = std::chrono::steady_clock::now();
    auto last_misc_refresh = std::chrono::steady_clock::now();
    auto last_logs_refresh = std::chrono::steady_clock::now();
    auto last_compose_refresh = std::chrono::steady_clock::now();

    while (state.running) {
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      if (!state.running) break;

      auto now = std::chrono::steady_clock::now();
      bool needs_redraw = false;

      // Auto-refresh containers + stats every 3 seconds
      if (std::chrono::duration_cast<std::chrono::seconds>(now - last_container_refresh).count() >= 3) {
        refresh_containers(state);
        last_container_refresh = now;
        needs_redraw = true;
      }

      // Auto-refresh misc every 15 seconds
      if (std::chrono::duration_cast<std::chrono::seconds>(now - last_misc_refresh).count() >= 15) {
        refresh_misc(state);
        last_misc_refresh = now;
        needs_redraw = true;
      }

      // Auto-refresh logs every 2 seconds when on logs tab
      bool on_logs_tab = false;
      {
          std::lock_guard<std::mutex> lock(state.mtx);
          on_logs_tab = (state.current_tab == Tab::Logs);
      }
      
      if (on_logs_tab) {
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_logs_refresh).count() >= 2) {
          std::string c_name;
          {
              std::lock_guard<std::mutex> lock(state.mtx);
              const Container *c = get_selected_container(state);
              if (c) c_name = c->name;
          }
          if (!c_name.empty()) {
            std::string logs = docker::get_logs(c_name, "100");
            std::lock_guard<std::mutex> lock(state.mtx);
            state.logs_content = logs;
          }
          last_logs_refresh = now;
          needs_redraw = true;
        }
      }

      // Auto-refresh compose logs every 3 seconds when on compose tab
      bool on_compose_tab = false;
      bool compose_avail = false;
      {
          std::lock_guard<std::mutex> lock(state.mtx);
          on_compose_tab = (state.current_tab == Tab::Compose);
          compose_avail = state.compose_available;
      }

      if (on_compose_tab && compose_avail) {
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_compose_refresh).count() >= 3) {
          std::string logs = docker::get_compose_logs();
          std::lock_guard<std::mutex> lock(state.mtx);
          state.compose_logs = logs;
          last_compose_refresh = now;
          needs_redraw = true;
        }
      }

      if (needs_redraw) {
        screen.PostEvent(Event::Custom);
      }
    }
  });

  screen.Loop(component);

  state.running = false;
  if (refresh_thread.joinable()) {
    refresh_thread.join();
  }
}

} // namespace ui
} // namespace nw
