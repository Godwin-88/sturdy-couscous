add_executable(test_parity test_parity.cpp)
target_link_libraries(test_parity PRIVATE riskengine Catch2::Catch2WithMain)
target_include_directories(test_parity PRIVATE ${CMAKE_SOURCE_DIR}/include ${CMAKE_SOURCE_DIR}/tests)
add_test(NAME parity COMMAND test_parity)
