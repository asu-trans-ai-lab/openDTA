cmake_minimum_required(VERSION 3.15.0)
project(OpenDTA VERSION 0.1.0)

include(CTest)
enable_testing()

option(PARALLEL ON)
configure_file(config.h.in config.h)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_BUILD_TYPE Release)

message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")

add_executable(${PROJECT_NAME} src/main.cpp src/elements.cpp src/simulation.cpp src/ue.cpp src/utils.cpp)

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)

include_directories(include)
target_include_directories(${PROJECT_NAME} PUBLIC ${PROJECT_BINARY_DIR})

# default name for Windows
set(YAML_CPP_LIB_NAME yaml-cpp)

if (CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    if(CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "arm64")
        set(YAML_CPP_LIB_NAME yaml-cpp_mac-arm)
    elseif(CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "x86_64")
        set(YAML_CPP_LIB_NAME yaml-cpp_mac-x86)
    endif()
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(YAML_CPP_LIB_NAME yaml-cpp_linux)
endif()

find_library(YAML_CPP NAMES ${YAML_CPP_LIB_NAME} PATHS lib NO_SYSTEM_ENVIRONMENT_PATH)
target_link_libraries(${PROJECT_NAME} PRIVATE ${YAML_CPP})

if (PARALLEL)
    message(STATUS "Build parallel version")
    find_package(OpenMP REQUIRED)
    target_link_libraries(${PROJECT_NAME} PRIVATE OpenMP::OpenMP_CXX)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${OpenMP_CXX_FLAGS}")
endif()

# simulation self-test harness: thin driver over the production sources
# (dev/self_test_simulation/simulation_self_test.yml is the test contract)
option(SELF_TEST "Build the simulation self-test harness" OFF)
if (SELF_TEST)
    add_executable(OpenDTA_self_test
        dev/self_test_simulation/self_test_simulation.cpp
        src/elements.cpp src/simulation.cpp src/ue.cpp src/utils.cpp)
    target_include_directories(OpenDTA_self_test PUBLIC ${PROJECT_BINARY_DIR})
    target_link_libraries(OpenDTA_self_test PRIVATE ${YAML_CPP})
    if (PARALLEL)
        target_link_libraries(OpenDTA_self_test PRIVATE OpenMP::OpenMP_CXX)
    endif()

    # ctest registration: the C++ harness plus the full python gate battery
    # (see dev/self_test_simulation/TESTING_VALIDATION_PLAN.md)
    add_test(NAME opendta_self_test
             COMMAND OpenDTA_self_test ${PROJECT_SOURCE_DIR}/dev/self_test_simulation
             WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}/dev/self_test_simulation)
    find_package(Python3 COMPONENTS Interpreter)
    if (Python3_FOUND)
        add_test(NAME opendta_gates
                 COMMAND ${Python3_EXECUTABLE} tools/run_all_gates.py --no-record
                 WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}/dev/self_test_simulation)
        set_tests_properties(opendta_gates PROPERTIES TIMEOUT 1800)
    endif()
endif()

# it is for std::experimental::filesystem in utils.cpp if g++ happens to be the compiler
if (CMAKE_COMPILER_IS_GNUCXX)
    target_link_libraries(${PROJECT_NAME} PRIVATE stdc++fs)
endif()
