#pragma once 
#include <chrono> 
#include <string>

namespace Utils::Time
{
	// Converter time from std::chrono to PostgreSQL 
	std::string to_pg_timestamp(std::chrono::system_clock::time_point tp);

	// Converter time from PostgreSQL to std::chrono
	std::chrono::system_clock::time_point from_pg_timestamp(const std::string& s);
}