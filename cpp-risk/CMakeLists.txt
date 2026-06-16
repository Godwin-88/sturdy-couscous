cmake_minimum_required(VERSION 3.20)
project(riskengine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# nlohmann/json (header-only)
FetchContent_Declare(
  nlohmann_json
  GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(nlohmann_json)

# Catch2 v3
FetchContent_Declare(
  catch2
  GIT_REPOSITORY https://github.com/catchorg/Catch2.git
  GIT_TAG v3.5.0
)
FetchContent_MakeAvailable(catch2)

enable_testing()

add_subdirectory(src)
add_subdirectory(tests)

add_executable(risk-engine src/main.cpp)
target_link_libraries(risk-engine PRIVATE riskengine hiredis pq)
target_include_directories(risk-engine PRIVATE ${CMAKE_SOURCE_DIR}/include)

# Postgres headers
target_include_directories(riskengine PUBLIC /usr/include/postgresql)
target_include_directories(risk-engine PRIVATE /usr/include/postgresql)
