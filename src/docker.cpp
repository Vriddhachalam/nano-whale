#include "docker.h"
#include "platform.h"

#include <algorithm>
#include <regex>
#include <sstream>
#include <fstream>

namespace nw {
namespace docker {

static std::string docker_exec(const std::string &cmd, int timeout_ms = 5000) {
  std::string full_cmd = platform::get_docker_cmd() + " " + cmd;
  auto result = platform::exec_command(full_cmd, timeout_ms);
  return result.value_or("");
}

bool is_available() {
  auto result =
      platform::exec_command(platform::get_docker_cmd() + " --version", 10000);
  return result.has_value() && !result->empty();
}

std::vector<Container> get_containers() {
  std::string out = docker_exec(
      "ps -a --format "
      "\"{{.Names}}|{{.Status}}|{{.ID}}|{{.Image}}|{{.Ports}}|{{.State}}\"");
  if (out.empty())
    return {};

  std::vector<Container> containers;
  auto lines = platform::split(out, '\n');
  for (const auto &line : lines) {
    if (line.empty())
      continue;
    auto parts = platform::split(line, '|');
    if (parts.size() < 6)
      continue;

    Container c;
    c.name = parts[0];
    c.status = parts[1];
    c.id = parts[2].substr(0, 12);
    c.image = parts[3];
    c.ports = parts[4];
    c.state = parts[5];
    containers.push_back(std::move(c));
  }
  return containers;
}

std::vector<Image> get_images() {
  std::string out = docker_exec(
      "images --format \"{{.Repository}}|{{.Tag}}|{{.Size}}|{{.ID}}\"");
  if (out.empty())
    return {};

  std::vector<Image> images;
  auto lines = platform::split(out, '\n');
  for (const auto &line : lines) {
    if (line.empty())
      continue;
    auto parts = platform::split(line, '|');
    if (parts.size() < 4)
      continue;

    Image img;
    img.repo = parts[0];
    img.tag = parts[1];
    img.size = parts[2];
    img.id = parts[3].substr(0, 12);
    images.push_back(std::move(img));
  }
  return images;
}

std::vector<Volume> get_volumes() {
  std::string out = docker_exec("volume ls --format \"{{.Driver}}|{{.Name}}\"");
  if (out.empty())
    return {};

  std::vector<Volume> volumes;
  auto lines = platform::split(out, '\n');
  for (const auto &line : lines) {
    if (line.empty())
      continue;
    auto parts = platform::split(line, '|');
    if (parts.size() < 2)
      continue;

    Volume v;
    v.driver = parts[0].empty() ? "local" : parts[0];
    v.name = parts[1].empty() ? "N/A" : parts[1];
    volumes.push_back(std::move(v));
  }
  return volumes;
}

std::vector<Network> get_networks() {
  std::string out =
      docker_exec("network ls --format \"{{.Driver}}|{{.Name}}\"");
  if (out.empty())
    return {};

  std::vector<Network> networks;
  auto lines = platform::split(out, '\n');
  for (const auto &line : lines) {
    if (line.empty())
      continue;
    auto parts = platform::split(line, '|');
    if (parts.size() < 2)
      continue;

    Network n;
    n.driver = parts[0].empty() ? "bridge" : parts[0];
    n.name = parts[1].empty() ? "N/A" : parts[1];
    networks.push_back(std::move(n));
  }
  return networks;
}

std::vector<std::string> get_container_env(const std::string &name) {
  std::string out = docker_exec(
      "inspect --format \"{{range .Config.Env}}{{println .}}{{end}}\" " + name);
  if (out.empty())
    return {};
  auto lines = platform::split(out, '\n');
  lines.erase(std::remove_if(lines.begin(), lines.end(),
                             [](const std::string &s) {
                               return platform::trim(s).empty();
                             }),
              lines.end());
  return lines;
}

std::string get_container_top(const std::string &name) {
  std::string out = docker_exec("top " + name);
  return out.empty() ? "Container not running" : out;
}

std::optional<nlohmann::json> get_container_inspect(const std::string &name) {
  std::string out = docker_exec("inspect " + name);
  if (out.empty())
    return std::nullopt;
  try {
    auto j = nlohmann::json::parse(out);
    if (j.is_array() && !j.empty()) {
      return j[0];
    }
    return j;
  } catch (...) {
    return std::nullopt;
  }
}

std::map<std::string, ContainerStats> get_stats_snapshot() {
  std::string out =
      docker_exec("stats --no-stream --format "
                  "\"{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}|{{."
                  "NetIO}}|{{.BlockIO}}|{{.PIDs}}\"",
                  15000);

  std::map<std::string, ContainerStats> stats;
  if (out.empty())
    return stats;

  auto lines = platform::split(out, '\n');
  for (const auto &line : lines) {
    if (line.empty())
      continue;
    auto parts = platform::split(line, '|');
    if (parts.size() < 7)
      continue;

    std::string name = platform::trim(parts[0]);
    if (name.empty())
      continue;

    ContainerStats cs;

    // Parse CPU percentage (remove '%')
    std::string cpu_str = parts[1];
    cpu_str.erase(std::remove(cpu_str.begin(), cpu_str.end(), '%'),
                  cpu_str.end());
    cpu_str = platform::trim(cpu_str);
    try {
      cs.cpu = std::stod(cpu_str);
    } catch (...) {
      cs.cpu = 0.0;
    }

    // Parse Memory percentage
    std::string mem_str = parts[2];
    mem_str.erase(std::remove(mem_str.begin(), mem_str.end(), '%'),
                  mem_str.end());
    mem_str = platform::trim(mem_str);
    try {
      cs.mem = std::stod(mem_str);
    } catch (...) {
      cs.mem = 0.0;
    }

    cs.mem_usage = platform::trim(parts[3]);
    cs.net_io = platform::trim(parts[4]);
    cs.block_io = platform::trim(parts[5]);
    cs.pids = platform::trim(parts[6]);

    stats[name] = cs;
  }
  return stats;
}

bool start_container(const std::string &name) {
  std::string out = docker_exec("start " + name, 30000);
  return !out.empty() || true; // docker start may return empty on success
}

bool stop_container(const std::string &name) {
  std::string out = docker_exec("stop " + name, 30000);
  return true;
}

bool restart_container(const std::string &name) {
  std::string out = docker_exec("restart " + name, 60000);
  return true;
}

bool delete_container(const std::string &name) {
  auto result = platform::exec_command(
      platform::get_docker_cmd() + " rm -f " + name, 30000);
  return result.has_value();
}

bool delete_image(const std::string &id) {
  auto result = platform::exec_command(
      platform::get_docker_cmd() + " rmi -f " + id, 30000);
  return result.has_value();
}

bool delete_volume(const std::string &name) {
  auto result = platform::exec_command(
      platform::get_docker_cmd() + " volume rm -f " + name, 30000);
  return result.has_value();
}

bool delete_network(const std::string &name) {
  auto result = platform::exec_command(
      platform::get_docker_cmd() + " network rm " + name, 5000);
  return result.has_value();
}

std::string get_logs(const std::string &name, const std::string &tail) {
  // Capture both stdout and stderr with 2>&1
  std::string cmd = "logs --tail " + tail + " " + name + " 2>&1";
  return docker_exec(cmd, 10000);
}
void system_prune() {
  platform::exec_command(platform::get_docker_cmd() + " system prune -f", 15000);
}

std::string inspect_container(const std::string& name) {
    auto res = platform::exec_command(platform::get_docker_cmd() + " inspect " + name, 5000);
    if (!res) return "Failed to inspect container.";
    
    try {
        auto j = nlohmann::json::parse(res.value());
        if (j.is_array() && !j.empty()) {
            auto& data = j[0];
            std::stringstream ss;
            
            ss << "=== Container: " << data.value("Name", "") << " ===\n\n";
            ss << "ID: " << data.value("Id", "") << "\n";
            ss << "State: " << data["State"].value("Status", "") << "\n\n";
            
            ss << "--- Network ---\n";
            if (data.contains("NetworkSettings") && data["NetworkSettings"].contains("Networks")) {
                for (auto& [net_name, net_val] : data["NetworkSettings"]["Networks"].items()) {
                    ss << net_name << " IP: " << net_val.value("IPAddress", "") << "\n";
                }
            }
            ss << "\n";
            
            ss << "--- Mounts ---\n";
            if (data.contains("Mounts")) {
                for (auto& mount : data["Mounts"]) {
                    ss << mount.value("Source", "") << "\n  -> " << mount.value("Destination", "") << "\n";
                }
            }
            ss << "\n";
            
            ss << "--- Environment Variables ---\n";
            if (data.contains("Config") && data["Config"].contains("Env")) {
                for (auto& env : data["Config"]["Env"]) {
                    ss << env.get<std::string>() << "\n";
                }
            }
            
            return ss.str();
        }
    } catch (...) {
        return "Failed to parse inspect output.";
    }
    return res.value(); // fallback
}

std::vector<FileEntry> list_files(const std::string& container, const std::string& path) {
    std::vector<FileEntry> files;
    auto res = platform::exec_command(platform::get_docker_cmd() + " exec " + container + " ls -lha " + path, 5000);
    if (!res) return files;
    
    auto lines = platform::split(res.value(), '\n');
    for (const auto& line : lines) {
        if (line.empty() || line.find("total") == 0) continue;
        
        std::istringstream iss(line);
        std::vector<std::string> tokens;
        std::string token;
        while (iss >> token) {
            tokens.push_back(token);
        }
        
        if (tokens.size() >= 9) {
            FileEntry entry;
            entry.permissions = tokens[0];
            entry.is_dir = (entry.permissions[0] == 'd');
            entry.size = tokens[4];
            entry.date = tokens[5] + " " + tokens[6] + " " + tokens[7];
            
            entry.name = tokens[8];
            for (size_t i = 9; i < tokens.size(); ++i) {
                entry.name += " " + tokens[i];
            }
            files.push_back(entry);
        }
    }
    return files;
}

void download_file(const std::string& container, const std::string& path) {
    std::string filename = path.substr(path.find_last_of('/') + 1);
    if (filename.empty()) filename = "downloaded_file";
    
    platform::exec_command(platform::get_docker_cmd() + " cp " + container + ":" + path + " ./" + filename, 15000);
}

bool has_docker_compose() {
    std::ifstream f1("docker-compose.yml");
    std::ifstream f2("docker-compose.yaml");
    std::ifstream f3("compose.yaml");
    std::ifstream f4("compose.yml");
    return f1.good() || f2.good() || f3.good() || f4.good();
}

void compose_up() {
    platform::exec_command(platform::get_docker_cmd() + " compose up -d", 60000);
}

void compose_down() {
    platform::exec_command(platform::get_docker_cmd() + " compose down", 60000);
}

std::string get_compose_logs() {
    auto res = platform::exec_command(platform::get_docker_cmd() + " compose logs --tail=100", 5000);
    return res.value_or("No logs available or project is down.");
}

} // namespace docker
} // namespace nw