#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <latch>
#include <mutex>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

struct Options {
    std::string mode = "both";
    int min_readers = 3;
    int max_readers = 8;
    int writers = 2;
    int trials = 3;
    int base_operations = 60;
    std::optional<int> student_id;
    DWORD read_work_us = 250;
    DWORD reader_think_us = 150;
    DWORD write_work_us = 150;
    DWORD jitter_us = 50;
    DWORD reader_phase_ms = 3;
    DWORD wait_timeout_ms = 30000;
    DWORD max_runtime_ms = 60000;
    std::uint32_t standard_seed = 42;
    bool verbose = false;
    std::filesystem::path output_dir = "data";
};

struct WaitTimeout : std::runtime_error {
    using std::runtime_error::runtime_error;
};

std::string win_error(const char* operation, DWORD error = GetLastError()) {
    std::ostringstream message;
    message << operation << " failed (GetLastError=" << error << ')';
    return message.str();
}

int parse_integer(const std::string& text, const char* name, int min_value, int max_value) {
    int value = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() ||
        value < min_value || value > max_value) {
        throw std::invalid_argument(std::string("Invalid value for ") + name + ": " + text);
    }
    return value;
}

void print_help() {
    std::cout
        << "Reader-priority readers-writers simulation (Windows API)\n"
        << "Options:\n"
        << "  --mode standard|individual|both   Experiment mode (default: both)\n"
        << "  --student-id 000..999             Required for individual/both\n"
        << "  --min-readers N                   First reader count (default: 3)\n"
        << "  --max-readers N                   Last reader count (default: 8)\n"
        << "  --writers N                       Writer threads (default: 2)\n"
        << "  --trials N                        Trials per configuration, at least 3\n"
        << "  --base-operations N               Standard operations per participant\n"
        << "  --read-work-us N                  Read critical-section work\n"
        << "  --reader-think-us N               Reader work between operations\n"
        << "  --write-work-us N                 Write critical-section work\n"
        << "  --jitter-us N                     Seeded work variation\n"
        << "  --reader-phase-ms N               Stagger reader start phases\n"
        << "  --wait-timeout-ms N               Per-wait timeout\n"
        << "  --max-runtime-ms N                Maximum duration of one trial\n"
        << "  --standard-seed N                 Standard-mode seed (default: 42)\n"
        << "  --output-dir PATH                 CSV destination (default: data)\n"
        << "  --verbose                         Print participant state transitions\n"
        << "  --help                            Show this help\n";
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help") {
            print_help();
            std::exit(0);
        }
        if (arg == "--verbose") {
            options.verbose = true;
            continue;
        }
        if (i + 1 >= argc) {
            throw std::invalid_argument("Missing value after " + arg);
        }
        const std::string value = argv[++i];
        if (arg == "--mode") {
            options.mode = value;
        } else if (arg == "--student-id") {
            options.student_id = parse_integer(value, "--student-id", 0, 999);
        } else if (arg == "--min-readers") {
            options.min_readers = parse_integer(value, "--min-readers", 1, 64);
        } else if (arg == "--max-readers") {
            options.max_readers = parse_integer(value, "--max-readers", 1, 64);
        } else if (arg == "--writers") {
            options.writers = parse_integer(value, "--writers", 1, 64);
        } else if (arg == "--trials") {
            options.trials = parse_integer(value, "--trials", 3, 1000);
        } else if (arg == "--base-operations") {
            options.base_operations = parse_integer(value, "--base-operations", 1, 100000);
        } else if (arg == "--read-work-us") {
            options.read_work_us =
                static_cast<DWORD>(parse_integer(value, "--read-work-us", 0, 1000000));
        } else if (arg == "--reader-think-us") {
            options.reader_think_us =
                static_cast<DWORD>(parse_integer(value, "--reader-think-us", 0, 1000000));
        } else if (arg == "--write-work-us") {
            options.write_work_us =
                static_cast<DWORD>(parse_integer(value, "--write-work-us", 0, 1000000));
        } else if (arg == "--jitter-us") {
            options.jitter_us =
                static_cast<DWORD>(parse_integer(value, "--jitter-us", 0, 1000000));
        } else if (arg == "--reader-phase-ms") {
            options.reader_phase_ms =
                static_cast<DWORD>(parse_integer(value, "--reader-phase-ms", 0, 1000));
        } else if (arg == "--wait-timeout-ms") {
            options.wait_timeout_ms =
                static_cast<DWORD>(parse_integer(value, "--wait-timeout-ms", 1, 3600000));
        } else if (arg == "--max-runtime-ms") {
            options.max_runtime_ms =
                static_cast<DWORD>(parse_integer(value, "--max-runtime-ms", 1, 3600000));
        } else if (arg == "--standard-seed") {
            options.standard_seed = static_cast<std::uint32_t>(
                parse_integer(value, "--standard-seed", 0, 2147483647));
        } else if (arg == "--output-dir") {
            options.output_dir = value;
        } else {
            throw std::invalid_argument("Unknown option: " + arg);
        }
    }

    if (options.mode != "standard" && options.mode != "individual" && options.mode != "both") {
        throw std::invalid_argument("--mode must be standard, individual, or both");
    }
    if (options.min_readers > options.max_readers) {
        throw std::invalid_argument("--min-readers must not exceed --max-readers");
    }
    if ((options.mode == "individual" || options.mode == "both") && !options.student_id) {
        throw std::invalid_argument("--student-id is required for individual/both mode");
    }
    return options;
}

struct RuntimeState {
    std::atomic<long long> successful_reads{0};
    std::atomic<long long> successful_writes{0};
    std::atomic<long long> active_reader_operations{0};
    std::atomic<int> writer_inside{0};
    std::atomic<int> timeouts{0};
    std::atomic<int> invariant_violations{0};
    std::atomic<int> cleanup_errors{0};
    std::atomic<bool> cancelled{false};
    std::mutex errors_mutex;
    std::vector<std::string> errors;

    void add_error(std::string error) {
        cancelled.store(true, std::memory_order_relaxed);
        std::lock_guard<std::mutex> guard(errors_mutex);
        errors.push_back(std::move(error));
    }
};

class WinHandle {
public:
    WinHandle(HANDLE handle, RuntimeState& state) : handle_(handle), state_(state) {
        if (handle_ == nullptr || handle_ == INVALID_HANDLE_VALUE) {
            throw std::runtime_error(win_error("Create synchronization object"));
        }
    }

    ~WinHandle() {
        close();
    }

    WinHandle(const WinHandle&) = delete;
    WinHandle& operator=(const WinHandle&) = delete;

    HANDLE get() const {
        return handle_;
    }

    void close() noexcept {
        if (handle_ == nullptr) {
            return;
        }
        if (!CloseHandle(handle_)) {
            state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
        }
        handle_ = nullptr;
    }

private:
    HANDLE handle_;
    RuntimeState& state_;
};

class WinMutexGuard {
public:
    WinMutexGuard(HANDLE mutex, DWORD timeout_ms, RuntimeState& state)
        : mutex_(mutex), state_(state) {
        const DWORD result = WaitForSingleObject(mutex_, timeout_ms);
        if (result == WAIT_OBJECT_0) {
            owns_ = true;
        } else if (result == WAIT_ABANDONED) {
            if (!ReleaseMutex(mutex_)) {
                state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
            }
            throw std::runtime_error("A Windows mutex was abandoned");
        } else if (result == WAIT_TIMEOUT) {
            throw WaitTimeout("Timed out waiting for a Windows mutex");
        } else {
            throw std::runtime_error(win_error("WaitForSingleObject(mutex)"));
        }
    }

    ~WinMutexGuard() {
        release_noexcept();
    }

    WinMutexGuard(const WinMutexGuard&) = delete;
    WinMutexGuard& operator=(const WinMutexGuard&) = delete;

    void release() {
        if (!owns_) {
            return;
        }
        owns_ = false;
        if (!ReleaseMutex(mutex_)) {
            state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
            throw std::runtime_error(win_error("ReleaseMutex"));
        }
    }

private:
    void release_noexcept() noexcept {
        if (owns_) {
            owns_ = false;
            if (!ReleaseMutex(mutex_)) {
                state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
            }
        }
    }

    HANDLE mutex_;
    RuntimeState& state_;
    bool owns_ = false;
};

class SemaphoreGuard {
public:
    SemaphoreGuard(HANDLE semaphore, DWORD timeout_ms, RuntimeState& state)
        : semaphore_(semaphore), state_(state) {
        const DWORD result = WaitForSingleObject(semaphore_, timeout_ms);
        if (result == WAIT_OBJECT_0) {
            owns_ = true;
        } else if (result == WAIT_TIMEOUT) {
            throw WaitTimeout("Timed out waiting for the resource semaphore");
        } else {
            throw std::runtime_error(win_error("WaitForSingleObject(semaphore)"));
        }
    }

    ~SemaphoreGuard() {
        release_noexcept();
    }

    SemaphoreGuard(const SemaphoreGuard&) = delete;
    SemaphoreGuard& operator=(const SemaphoreGuard&) = delete;

    void release() {
        if (!owns_) {
            return;
        }
        owns_ = false;
        if (!ReleaseSemaphore(semaphore_, 1, nullptr)) {
            state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
            throw std::runtime_error(win_error("ReleaseSemaphore"));
        }
    }

    void relinquish_to_reader_group() {
        owns_ = false;
    }

private:
    void release_noexcept() noexcept {
        if (owns_) {
            owns_ = false;
            if (!ReleaseSemaphore(semaphore_, 1, nullptr)) {
                state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
            }
        }
    }

    HANDLE semaphore_;
    RuntimeState& state_;
    bool owns_ = false;
};

class ReaderPreferenceLock {
public:
    explicit ReaderPreferenceLock(RuntimeState& state)
        : state_(state),
          readers_mutex_(CreateMutexW(nullptr, FALSE, nullptr), state),
          resource_(CreateSemaphoreW(nullptr, 1, 1, nullptr), state) {}

    void lock_shared(DWORD timeout_ms) {
        const auto deadline = Clock::now() + std::chrono::milliseconds(timeout_ms);
        WinMutexGuard readers_guard(readers_mutex_.get(), timeout_ms, state_);
        if (active_readers_ == 0) {
            const auto remaining = std::chrono::ceil<std::chrono::milliseconds>(deadline - Clock::now()).count();
            if (remaining <= 0) {
                throw WaitTimeout("Reader acquisition deadline expired");
            }
            SemaphoreGuard resource_guard(resource_.get(), static_cast<DWORD>(remaining), state_);
            resource_guard.relinquish_to_reader_group();
        }
        ++active_readers_;
        readers_guard.release();
    }

    void unlock_shared() {
        WinMutexGuard readers_guard(readers_mutex_.get(), INFINITE, state_);
        if (active_readers_ <= 0) {
            state_.invariant_violations.fetch_add(1, std::memory_order_relaxed);
            throw std::logic_error("Reader count underflow");
        }
        --active_readers_;
        if (active_readers_ == 0 && !ReleaseSemaphore(resource_.get(), 1, nullptr)) {
            state_.cleanup_errors.fetch_add(1, std::memory_order_relaxed);
            throw std::runtime_error(win_error("ReleaseSemaphore(last reader)"));
        }
        readers_guard.release();
    }

    HANDLE resource() const {
        return resource_.get();
    }

    int active_readers() {
        WinMutexGuard readers_guard(readers_mutex_.get(), INFINITE, state_);
        const int count = active_readers_;
        readers_guard.release();
        return count;
    }

    void close() noexcept {
        resource_.close();
        readers_mutex_.close();
    }

private:
    RuntimeState& state_;
    WinHandle readers_mutex_;
    WinHandle resource_;
    int active_readers_ = 0;
};

class ReadGuard {
public:
    ReadGuard(ReaderPreferenceLock& lock, DWORD timeout_ms, RuntimeState& state)
        : lock_(lock), state_(state) {
        lock_.lock_shared(timeout_ms);
        owns_ = true;
    }

    ~ReadGuard() {
        if (owns_) {
            try {
                lock_.unlock_shared();
            } catch (const std::exception& error) {
                state_.add_error(std::string("Reader unlock: ") + error.what());
            }
        }
    }

    ReadGuard(const ReadGuard&) = delete;
    ReadGuard& operator=(const ReadGuard&) = delete;

    void release() {
        owns_ = false;
        lock_.unlock_shared();
    }

private:
    ReaderPreferenceLock& lock_;
    RuntimeState& state_;
    bool owns_ = false;
};

class WriteGuard {
public:
    WriteGuard(ReaderPreferenceLock& lock, DWORD timeout_ms, RuntimeState& state)
        : resource_guard_(lock.resource(), timeout_ms, state) {}

    void release() {
        resource_guard_.release();
    }

private:
    SemaphoreGuard resource_guard_;
};

class EventLogger {
public:
    EventLogger(bool enabled, RuntimeState& state, Clock::time_point start)
        : enabled_(enabled),
          state_(state),
          start_(start),
          mutex_(CreateMutexW(nullptr, FALSE, nullptr), state) {}

    void event(const std::string& participant, DWORD tid, const char* state, int operation) {
        if (!enabled_) {
            return;
        }
        try {
            WinMutexGuard guard(mutex_.get(), 5000, state_);
            const auto elapsed =
                std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - start_).count();
            std::cout << '[' << std::setw(8) << elapsed << " ms] "
                      << participant << " | TID=" << tid
                      << " | STATE=" << state << " | RESOURCE=1";
            if (operation > 0) {
                std::cout << " | OP=" << operation;
            }
            std::cout << '\n';
            guard.release();
        } catch (const std::exception& error) {
            state_.add_error(std::string("Event logger: ") + error.what());
        }
    }

    void close() noexcept {
        mutex_.close();
    }

private:
    bool enabled_;
    RuntimeState& state_;
    Clock::time_point start_;
    WinHandle mutex_;
};

struct TrialResult {
    std::string mode;
    int reader_count = 0;
    int trial = 0;
    std::uint32_t seed = 0;
    int operations_per_participant = 0;
    double elapsed_ms = 0.0;
    long long successful_reads = 0;
    long long successful_writes = 0;
    double average_writer_wait_ms = 0.0;
    double maximum_writer_wait_ms = 0.0;
    long long writer_wait_samples = 0;
    int timeouts = 0;
    int invariant_violations = 0;
    double throughput_ops_per_second = 0.0;
    std::vector<std::string> errors;
};

DWORD wait_timeout_until(Clock::time_point deadline, DWORD configured_timeout_ms) {
    const auto now = Clock::now();
    if (now >= deadline) {
        throw WaitTimeout("Trial deadline expired");
    }
    const auto remaining =
        std::chrono::ceil<std::chrono::milliseconds>(deadline - now).count();
    return static_cast<DWORD>(std::min<long long>(remaining, configured_timeout_ms));
}

void perform_work(DWORD base_us, DWORD jitter_us, std::mt19937& random) {
    std::uniform_int_distribution<DWORD> distribution(0, jitter_us);
    const DWORD duration_us = base_us + (jitter_us == 0 ? 0 : distribution(random));
    if (duration_us == 0) {
        SwitchToThread();
        return;
    }

    const auto deadline = Clock::now() + std::chrono::microseconds(duration_us);
    volatile std::uint64_t workload = 1;
    while (Clock::now() < deadline) {
        workload = workload * 1664525u + 1013904223u;
    }
    (void)workload;
}

TrialResult run_trial(const Options& options,
                      const std::string& mode,
                      int reader_count,
                      int operations,
                      int trial,
                      std::uint32_t seed) {
    RuntimeState state;
    ReaderPreferenceLock lock(state);
    const auto start = Clock::now();
    const auto deadline = start + std::chrono::milliseconds(options.max_runtime_ms);
    EventLogger logger(options.verbose, state, start);
    long long shared_value = 0;
    std::latch readers_started(reader_count);
    std::vector<std::vector<double>> writer_waits(options.writers);
    std::vector<std::jthread> readers;
    std::vector<std::jthread> writers;
    struct JoinOnExit {
        std::vector<std::jthread>& readers;
        std::vector<std::jthread>& writers;
        ~JoinOnExit() {
            for (auto& thread : readers) if (thread.joinable()) thread.join();
            for (auto& thread : writers) if (thread.joinable()) thread.join();
        }
    } join_on_exit{readers, writers};
    readers.reserve(reader_count);
    writers.reserve(options.writers);

    auto report_timeout = [&](const std::string& participant, DWORD tid, int operation) {
        state.timeouts.fetch_add(1, std::memory_order_relaxed);
        logger.event(participant, tid, "TIMEOUT", operation);
    };

    for (int i = 0; i < reader_count; ++i) {
        readers.emplace_back([&, i] {
            const std::string participant = "R" + std::to_string(i + 1);
            const DWORD tid = GetCurrentThreadId();
            bool announced = false;
            std::mt19937 random(seed + static_cast<std::uint32_t>((i + 1) * 0x9E3779B9u));
            logger.event(participant, tid, "STARTED", 0);
            try {
                if (options.reader_phase_ms > 0) {
                    const int phase_index =
                        (i + static_cast<int>(seed % static_cast<std::uint32_t>(reader_count))) %
                        reader_count;
                    Sleep(static_cast<DWORD>(phase_index) * options.reader_phase_ms);
                }
                for (int operation = 1; operation <= operations; ++operation) {
                    if (state.cancelled.load(std::memory_order_relaxed)) {
                        break;
                    }
                    if (Clock::now() >= deadline) {
                        report_timeout(participant, tid, operation);
                        break;
                    }
                    logger.event(participant, tid, "WAITING", operation);
                    try {
                        const DWORD timeout = wait_timeout_until(deadline, options.wait_timeout_ms);
                        ReadGuard guard(lock, timeout, state);
                        if (!announced) {
                            readers_started.count_down();
                            announced = true;
                        }
                        if (state.writer_inside.load(std::memory_order_relaxed) != 0) {
                            state.invariant_violations.fetch_add(1, std::memory_order_relaxed);
                            state.cancelled.store(true, std::memory_order_relaxed);
                        } else {
                            state.active_reader_operations.fetch_add(1, std::memory_order_relaxed);
                            logger.event(participant, tid, "READING", operation);
                            const long long snapshot = shared_value;
                            (void)snapshot;
                            perform_work(options.read_work_us, options.jitter_us, random);
                            state.successful_reads.fetch_add(1, std::memory_order_relaxed);
                            const long long active =
                                state.active_reader_operations.fetch_sub(1, std::memory_order_relaxed);
                            if (active <= 0) {
                                state.invariant_violations.fetch_add(1, std::memory_order_relaxed);
                            }
                        }
                        guard.release();
                    } catch (const WaitTimeout&) {
                        report_timeout(participant, tid, operation);
                        break;
                    }
                    if (operation < operations && options.reader_think_us > 0) {
                        logger.event(participant, tid, "THINKING", operation);
                        perform_work(options.reader_think_us, options.jitter_us, random);
                    }
                }
            } catch (const std::exception& error) {
                if (!announced) {
                    readers_started.count_down();
                    announced = true;
                }
                state.add_error(participant + ": " + error.what());
            }
            if (!announced) {
                readers_started.count_down();
            }
            logger.event(participant, tid, "FINISHED", 0);
        });
    }

    readers_started.wait();

    for (int i = 0; i < options.writers; ++i) {
        writers.emplace_back([&, i] {
            const std::string participant = "W" + std::to_string(i + 1);
            const DWORD tid = GetCurrentThreadId();
            std::mt19937 random(seed + static_cast<std::uint32_t>((reader_count + i + 1) * 0x9E3779B9u));
            logger.event(participant, tid, "STARTED", 0);
            try {
                for (int operation = 1; operation <= operations; ++operation) {
                    if (state.cancelled.load(std::memory_order_relaxed)) {
                        break;
                    }
                    if (Clock::now() >= deadline) {
                        report_timeout(participant, tid, operation);
                        break;
                    }
                    logger.event(participant, tid, "WAITING", operation);
                    const auto wait_start = Clock::now();
                    try {
                        const DWORD timeout = wait_timeout_until(deadline, options.wait_timeout_ms);
                        WriteGuard guard(lock, timeout, state);
                        const auto acquired = Clock::now();
                        writer_waits[i].push_back(
                            std::chrono::duration<double, std::milli>(acquired - wait_start).count());

                        int expected = 0;
                        const bool exclusive = state.writer_inside.compare_exchange_strong(
                            expected, 1, std::memory_order_relaxed);
                        if (!exclusive ||
                            state.active_reader_operations.load(std::memory_order_relaxed) != 0) {
                            state.invariant_violations.fetch_add(1, std::memory_order_relaxed);
                            state.cancelled.store(true, std::memory_order_relaxed);
                            if (exclusive) {
                                state.writer_inside.store(0, std::memory_order_relaxed);
                            }
                        } else {
                            logger.event(participant, tid, "WRITING", operation);
                            ++shared_value;
                            perform_work(options.write_work_us, options.jitter_us, random);
                            state.successful_writes.fetch_add(1, std::memory_order_relaxed);
                            state.writer_inside.store(0, std::memory_order_relaxed);
                        }
                        guard.release();
                    } catch (const WaitTimeout&) {
                        report_timeout(participant, tid, operation);
                        break;
                    }
                }
            } catch (const std::exception& error) {
                state.add_error(participant + ": " + error.what());
                state.writer_inside.store(0, std::memory_order_relaxed);
            }
            logger.event(participant, tid, "FINISHED", 0);
        });
    }

    for (auto& reader : readers) {
        reader.join();
    }
    for (auto& writer : writers) {
        writer.join();
    }

    const int readers_left = lock.active_readers();
    if (readers_left != 0 ||
        shared_value != state.successful_writes.load(std::memory_order_relaxed) ||
        state.active_reader_operations.load(std::memory_order_relaxed) != 0 ||
        state.writer_inside.load(std::memory_order_relaxed) != 0) {
        state.invariant_violations.fetch_add(1, std::memory_order_relaxed);
    }

    logger.close();
    lock.close();
    const auto finish = Clock::now();

    TrialResult result;
    result.mode = mode;
    result.reader_count = reader_count;
    result.trial = trial;
    result.seed = seed;
    result.operations_per_participant = operations;
    result.elapsed_ms = std::chrono::duration<double, std::milli>(finish - start).count();
    result.successful_reads = state.successful_reads.load(std::memory_order_relaxed);
    result.successful_writes = state.successful_writes.load(std::memory_order_relaxed);
    result.timeouts = state.timeouts.load(std::memory_order_relaxed);
    result.invariant_violations =
        state.invariant_violations.load(std::memory_order_relaxed) +
        state.cleanup_errors.load(std::memory_order_relaxed);
    result.errors = std::move(state.errors);

    for (const auto& waits : writer_waits) {
        for (const double wait : waits) {
            result.average_writer_wait_ms += wait;
            result.maximum_writer_wait_ms = std::max(result.maximum_writer_wait_ms, wait);
            ++result.writer_wait_samples;
        }
    }
    if (result.writer_wait_samples > 0) {
        result.average_writer_wait_ms /= result.writer_wait_samples;
    }
    if (result.elapsed_ms > 0.0) {
        result.throughput_ops_per_second =
            1000.0 * (result.successful_reads + result.successful_writes) / result.elapsed_ms;
    }

    const long long expected_reads = static_cast<long long>(reader_count) * operations;
    const long long expected_writes = static_cast<long long>(options.writers) * operations;
    if (result.timeouts == 0 &&
        (result.successful_reads != expected_reads || result.successful_writes != expected_writes)) {
        ++result.invariant_violations;
    }
    return result;
}

void write_csv_header(std::ofstream& output) {
    output << "mode,reader_count,trial,seed,operations_per_participant,elapsed_ms,"
              "successful_reads,successful_writes,average_writer_wait_ms,"
              "maximum_writer_wait_ms,writer_wait_samples,timeouts,invariant_violations,"
              "throughput_ops_per_second,writer_count,student_id,read_work_us,reader_think_us,"
              "write_work_us,jitter_us,reader_phase_ms,wait_timeout_ms,max_runtime_ms\n";
}

void write_csv_row(std::ofstream& output, const TrialResult& result, const Options& options) {
    output << result.mode << ',' << result.reader_count << ',' << result.trial << ','
           << result.seed << ',' << result.operations_per_participant << ','
           << std::fixed << std::setprecision(6) << result.elapsed_ms << ','
           << result.successful_reads << ',' << result.successful_writes << ','
           << result.average_writer_wait_ms << ',' << result.maximum_writer_wait_ms << ','
           << result.writer_wait_samples << ',' << result.timeouts << ','
           << result.invariant_violations << ',' << result.throughput_ops_per_second << ','
           << options.writers << ',' << (options.student_id ? std::to_string(*options.student_id) : "") << ','
           << options.read_work_us << ',' << options.reader_think_us << ','
           << options.write_work_us << ',' << options.jitter_us << ','
           << options.reader_phase_ms << ','
           << options.wait_timeout_ms << ',' << options.max_runtime_ms << '\n';
}

bool run_mode(const Options& options, const std::string& mode, int operations, std::uint32_t base_seed) {
    std::filesystem::create_directories(options.output_dir);
    const auto output_path = options.output_dir / (mode + ".csv");
    std::ofstream output(output_path, std::ios::trunc);
    if (!output) {
        throw std::runtime_error("Cannot open output file: " + output_path.string());
    }
    write_csv_header(output);

    std::cout << "\nMode: " << mode << " | operations/participant=" << operations
              << " | seed=" << base_seed << " | trials/configuration=" << options.trials << '\n';
    std::cout << std::left << std::setw(9) << "Readers"
              << std::right << std::setw(8) << "Trial"
              << std::setw(15) << "Elapsed(ms)"
              << std::setw(18) << "Avg wait(ms)"
              << std::setw(14) << "Reads"
              << std::setw(14) << "Writes"
              << std::setw(12) << "Timeouts"
              << std::setw(12) << "Violations" << '\n';

    bool successful = true;
    for (int reader_count = options.min_readers; reader_count <= options.max_readers; ++reader_count) {
        std::vector<double> elapsed_times;
        std::vector<double> writer_wait_averages;
        for (int trial = 1; trial <= options.trials; ++trial) {
            const std::uint32_t trial_seed = base_seed + static_cast<std::uint32_t>(trial - 1);
            TrialResult result =
                run_trial(options, mode, reader_count, operations, trial, trial_seed);
            write_csv_row(output, result, options);
            output.flush();
            if (!output) {
                throw std::runtime_error("Failed while writing CSV file: " + output_path.string());
            }

            std::cout << std::left << std::setw(9) << reader_count
                      << std::right << std::setw(8) << trial
                      << std::fixed << std::setprecision(3)
                      << std::setw(15) << result.elapsed_ms
                      << std::setw(18) << result.average_writer_wait_ms
                      << std::setw(14) << result.successful_reads
                      << std::setw(14) << result.successful_writes
                      << std::setw(12) << result.timeouts
                      << std::setw(12) << result.invariant_violations << '\n';

            elapsed_times.push_back(result.elapsed_ms);
            writer_wait_averages.push_back(result.average_writer_wait_ms);
            if (result.invariant_violations != 0 || result.timeouts != 0 || !result.errors.empty()) {
                successful = false;
                for (const auto& error : result.errors) {
                    std::cerr << "ERROR: " << error << '\n';
                }
            }
        }
        double mean_elapsed = 0.0;
        double mean_writer_wait = 0.0;
        for (std::size_t i = 0; i < elapsed_times.size(); ++i) {
            mean_elapsed += elapsed_times[i];
            mean_writer_wait += writer_wait_averages[i];
        }
        mean_elapsed /= elapsed_times.size();
        mean_writer_wait /= writer_wait_averages.size();
        std::cout << "MEAN    " << reader_count << " readers: elapsed="
                  << std::fixed << std::setprecision(3) << mean_elapsed
                  << " ms, writer wait=" << mean_writer_wait << " ms\n";
    }
    std::cout << "Raw measurements: " << output_path.string() << '\n';
    return successful;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        bool successful = true;
        if (options.mode == "standard" || options.mode == "both") {
            successful = run_mode(options,
                                  "standard",
                                  options.base_operations,
                                  options.standard_seed) &&
                         successful;
        }
        if (options.mode == "individual" || options.mode == "both") {
            const int student_id = *options.student_id;
            const int operations = options.base_operations + student_id * 5;
            const std::uint32_t seed = 1000u + static_cast<std::uint32_t>(student_id) * 97u;
            successful = run_mode(options, "individual", operations, seed) && successful;
        }
        std::cout << "\nAll invariant checks passed: " << (successful ? "yes" : "no") << '\n';
        return successful ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << "ERROR: " << error.what() << '\n';
        return 1;
    }
}
