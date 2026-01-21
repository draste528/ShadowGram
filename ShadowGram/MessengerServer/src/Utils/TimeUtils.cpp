#include <chrono> 
#include <string>
#include <sstream>
#include <ctime>

namespace Utils::Time
{
	// Converter time from std::chrono to PostgreSQL 
	std::string to_pg_timestamp(std::chrono::system_clock::time_point tp)
	{
		std::time_t t = std::chrono::system_clock::to_time_t(tp);
		std::tm tm{};
		gmtime_s(&tm, &t); // windows !!!

		char buf[32];
		std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tm);
		return buf;
	}


	// Converter time from PostgreSQL to std::chrono
	std::chrono::system_clock::time_point from_pg_timestamp(const std::string& s)
	{
		std::tm tm{};
		std::istringstream ss(s);
		ss >> std::get_time(&tm, "%Y-%m-%d %H:%M:%S");

		if (ss.fail()) throw std::runtime_error("Invalid timestamp format from DB.");

		return std::chrono::system_clock::from_time_t(_mkgmtime(&tm)); // _mkgmtime - windows
	}
}