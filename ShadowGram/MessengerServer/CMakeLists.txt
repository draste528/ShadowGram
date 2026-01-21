cmake_minimum_required(VERSION 3.22)
project(MessengerServer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 4. Find Required Libraries (via vcpkg)
# NOW this will work, because project() has activated vcpkg
find_package(asio REQUIRED)
find_package(libpqxx REQUIRED)
find_package(unofficial-argon2 CONFIG REQUIRED)
find_package(stduuid CONFIG REQUIRED)
find_package(nlohmann_json REQUIRED)

add_executable(MessengerServer
    src/main.cpp
    src/Network/Server.cpp
    src/Network/Session.cpp
    src/Repositories/PostgresMessageRepository.cpp
    src/Repositories/PostgresUserRepository.cpp
    src/Services/AuthService.cpp
    src/Utils/TimeUtils.cpp
    "include/Entities/User.h"
    "include/Repositories/PostgresMessageRepository.h"
)

target_include_directories(MessengerServer
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

# 6. Link Libraries
target_link_libraries(MessengerServer
    PRIVATE
        asio::asio
        libpqxx::pqxx
        stduuid
        unofficial::argon2::libargon2
        nlohmann_json::nlohmann_json
)

if(WIN32)
    target_compile_definitions(MessengerServer PRIVATE _WIN32_WINNT=0x0A00)
    target_link_libraries(MessengerServer PRIVATE ws2_32 crypt32)
else()
    target_link_libraries(MessengerServer PRIVATE pthread)
endif()

#for Debugging
message(STATUS "Configured ShadowGram Server with C++20")