#pragma once

#include <string>
#include <vector>
#include <map>
#include <optional>
#include <nlohmann/json.hpp>

namespace nw {

/// Represents a Docker container.
struct Container {
    std::string name;
    std::string status;
    std::string id;
    std::string image;
    std::string ports;
    std::string state;  // "running", "exited", etc.

    bool is_running() const { return state == "running"; }
};

/// Represents a Docker image.
struct Image {
    std::string repo;
    std::string tag;
    std::string size;
    std::string id;
};

/// Represents a Docker volume.
struct Volume {
    std::string driver;
    std::string name;
};

/// Represents a Docker network.
struct Network {
    std::string driver;
    std::string name;
};

/// Container stats snapshot.
struct ContainerStats {
    double cpu = 0.0;
    double mem = 0.0;
    std::string mem_usage = "N/A";
    std::string net_io = "N/A";
    std::string block_io = "N/A";
    std::string pids = "N/A";
};

namespace docker {

/// Check if Docker is accessible.
bool is_available();

/// Fetch all containers.
std::vector<Container> get_containers();

/// Fetch all images.
std::vector<Image> get_images();

/// Fetch all volumes.
std::vector<Volume> get_volumes();

/// Fetch all networks.
std::vector<Network> get_networks();

/// Get environment variables for a container.
std::vector<std::string> get_container_env(const std::string& name);

/// Get top processes for a container.
std::string get_container_top(const std::string& name);

/// Get full inspect JSON for a container.
std::optional<nlohmann::json> get_container_inspect(const std::string& name);

/// Parse a single stats snapshot (from `docker stats --no-stream`).
std::map<std::string, ContainerStats> get_stats_snapshot();

/// Container actions.
bool start_container(const std::string& name);
bool stop_container(const std::string& name);
bool restart_container(const std::string& name);
bool delete_container(const std::string& name);
bool delete_image(const std::string& id);
bool delete_volume(const std::string& name);
bool delete_network(const std::string& name);

/// Get recent logs for a container.
std::string get_logs(const std::string& name, const std::string& tail = "100");

/// Execute docker system prune -f
void system_prune();

/// Inspect a container and format the output
std::string inspect_container(const std::string& name);

struct FileEntry {
    std::string permissions;
    std::string size;
    std::string date;
    std::string name;
    bool is_dir = false;
};

/// List files inside a container at a specific path
std::vector<FileEntry> list_files(const std::string& container, const std::string& path);

/// Download a file from a container to the local directory
void download_file(const std::string& container, const std::string& path);

// ── Docker Compose ──────────────────────────────────────────────────────

/// Check if docker-compose.yml or compose.yaml exists in the current directory
bool has_docker_compose();

/// Run docker compose up -d
void compose_up();

/// Run docker compose down
void compose_down();

/// Get docker compose logs
std::string get_compose_logs();

} // namespace docker
} // namespace nw
