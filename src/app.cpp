#include "app.h"

#include <algorithm>

namespace nw {

void refresh_all(AppState& state) {
    std::lock_guard<std::mutex> lock(state.mtx);
    state.containers = docker::get_containers();
    state.images = docker::get_images();
    state.volumes = docker::get_volumes();
    state.networks = docker::get_networks();
    
    state.compose_available = docker::has_docker_compose();
    if (state.compose_available && state.current_tab == Tab::Compose) {
        state.compose_logs = docker::get_compose_logs();
    }

    // Clamp selection indices
    if (!state.containers.empty()) {
        state.selected_container = std::clamp(
            state.selected_container, 0, static_cast<int>(state.containers.size()) - 1);
    } else {
        state.selected_container = 0;
    }
    if (!state.images.empty()) {
        state.selected_image = std::clamp(
            state.selected_image, 0, static_cast<int>(state.images.size()) - 1);
    }
    if (!state.volumes.empty()) {
        state.selected_volume = std::clamp(
            state.selected_volume, 0, static_cast<int>(state.volumes.size()) - 1);
    }
    if (!state.networks.empty()) {
        state.selected_network = std::clamp(
            state.selected_network, 0, static_cast<int>(state.networks.size()) - 1);
    }

    // Clear caches
    state.env_cache.clear();
    state.config_cache.clear();
    state.top_cache.clear();
}

void refresh_containers(AppState& state) {
    auto containers = docker::get_containers();
    auto stats_snap = docker::get_stats_snapshot();

    std::lock_guard<std::mutex> lock(state.mtx);
    state.containers = std::move(containers);

    // Update stats and history
    for (const auto& [name, cs] : stats_snap) {
        state.stats[name] = cs;

        state.cpu_history[name].push_back(cs.cpu);
        state.mem_history[name].push_back(cs.mem);

        if (static_cast<int>(state.cpu_history[name].size()) > MAX_HISTORY)
            state.cpu_history[name].pop_front();
        if (static_cast<int>(state.mem_history[name].size()) > MAX_HISTORY)
            state.mem_history[name].pop_front();
    }

    if (!state.containers.empty()) {
        state.selected_container = std::clamp(
            state.selected_container, 0, static_cast<int>(state.containers.size()) - 1);
    }
}

void refresh_misc(AppState& state) {
    auto images = docker::get_images();
    auto volumes = docker::get_volumes();
    auto networks = docker::get_networks();

    std::lock_guard<std::mutex> lock(state.mtx);
    state.images = std::move(images);
    state.volumes = std::move(volumes);
    state.networks = std::move(networks);

    if (!state.images.empty()) {
        state.selected_image = std::clamp(
            state.selected_image, 0, static_cast<int>(state.images.size()) - 1);
    }
    if (!state.volumes.empty()) {
        state.selected_volume = std::clamp(
            state.selected_volume, 0, static_cast<int>(state.volumes.size()) - 1);
    }
    if (!state.networks.empty()) {
        state.selected_network = std::clamp(
            state.selected_network, 0, static_cast<int>(state.networks.size()) - 1);
    }
}

const Container* get_selected_container(const AppState& state) {
    if (state.containers.empty() ||
        state.selected_container < 0 ||
        state.selected_container >= static_cast<int>(state.containers.size())) {
        return nullptr;
    }
    return &state.containers[state.selected_container];
}

} // namespace nw
