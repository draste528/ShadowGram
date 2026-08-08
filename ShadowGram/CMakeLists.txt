# ---
# Top-Level CMake file for ShadowGram Solution
# ---
cmake_minimum_required(VERSION 3.22)

# 1. Define the Solution Project
# We just give it a name
project(ShadowGram)

# 2. Include the server sub-project
# This is the ONLY thing this file should do.
#add_subdirectory(MessengerServer)

# ---------------------------------
# 1. Сначала находим пакеты, иначе target_link_libraries их не увидит
find_package(asio CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)

# 2. Подключаем сервер (он внутри себя тоже их подхватит)
add_subdirectory(MessengerServer)

# 3. Настраиваем временный клиент
#add_executable(MessengerClient MessengerClient/src/main.cpp)

# Указываем правильные имена таргетов из vcpkg
# Для asio это обычно asio::asio (как подсказал лог выше)
#target_link_libraries(MessengerClient PRIVATE 
#    asio::asio 
#    nlohmann_json::nlohmann_json
#)