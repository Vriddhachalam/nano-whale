cmake_minimum_required(VERSION 3.14)
project(nano-whale VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Fetch FTXUI
include(FetchContent)
FetchContent_Declare(ftxui
  GIT_REPOSITORY https://github.com/ArthurSonzogni/FTXUI
  GIT_TAG v5.0.0
)
set(FTXUI_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(FTXUI_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(FTXUI_BUILD_DOCS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(ftxui)

# Fetch nlohmann/json for JSON parsing (docker inspect)
FetchContent_Declare(json
  GIT_REPOSITORY https://github.com/nlohmann/json
  GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(json)

add_executable(nano-whale
  src/main.cpp
  src/app.cpp
  src/docker.cpp
  src/ui.cpp
  src/charts.cpp
  src/platform.cpp
)

target_include_directories(nano-whale PRIVATE src)

target_link_libraries(nano-whale PRIVATE
  ftxui::screen
  ftxui::dom
  ftxui::component
  nlohmann_json::nlohmann_json
)

# Platform-specific linking
if(WIN32)
  target_compile_definitions(nano-whale PRIVATE _WIN32_WINNT=0x0601)
endif()

if(UNIX AND NOT APPLE)
  find_package(Threads REQUIRED)
  target_link_libraries(nano-whale PRIVATE Threads::Threads)
endif()
