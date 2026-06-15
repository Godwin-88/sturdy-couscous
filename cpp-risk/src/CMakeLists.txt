add_library(riskengine STATIC
  Config.cpp
  Signal.cpp
  ApprovedOrder.cpp
  RiskEngine.cpp
)
target_include_directories(riskengine PUBLIC ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(riskengine PUBLIC nlohmann_json::nlohmann_json)
