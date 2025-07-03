local STATE_FILE = "/tmp/fluent_bit_state.txt"
local BUFFER_LIMIT = 100
local log_buffer = {}

function read_state()
    local file = io.open(STATE_FILE, "r")
    if not file then
        local default_state = {
            logging_enabled = false,
            logs_processed = 0,
            max_logs = 100
        }
        write_state(default_state)
        return default_state
    end

    local content = file:read("*all")
    file:close()
    local state = {
        logging_enabled = false,
        logs_processed = 0,
        max_logs = 100
    }

    for line in content:gmatch("[^\r\n]+") do
        local key, value = line:match("([^=]+)=([^=]+)")
        if key and value then
            key = key:gsub("^%s*(.-)%s*$", "%1")
            value = value:gsub("^%s*(.-)%s*$", "%1")
            if key == "logging_enabled" then
                state[key] = (value == "true")
            elseif key == "logs_processed" or key == "max_logs" then
                state[key] = tonumber(value) or state[key]
            end
        end
    end

    return state
end

function write_state(state)
    local temp_file = STATE_FILE .. ".tmp"
    local file = io.open(temp_file, "w")
    if file then
        file:write("logging_enabled=" .. tostring(state.logging_enabled) .. "\n")
        file:write("logs_processed=" .. tostring(state.logs_processed) .. "\n")
        file:write("max_logs=" .. tostring(state.max_logs) .. "\n")
        file:close()
        os.rename(temp_file, STATE_FILE)
        return true
    end
    return false
end

function init()
    local file = io.open(STATE_FILE, "r")
    if file then file:close() return end
    write_state({
        logging_enabled = false,
        logs_processed = 0,
        max_logs = 100
    })
end

function control_handler(tag, ts, record)
    local state = read_state()
    local action = record["action"]

    if action == "enable" then
        state.logging_enabled = true
        state.logs_processed = 0
        if record["max_logs"] then
            state.max_logs = tonumber(record["max_logs"]) or 100
        end
        write_state(state)
        print("Logging ENABLED")
    elseif action == "disable" then
        state.logging_enabled = false
        state.logs_processed = 0
        write_state(state)
        print("Logging DISABLED")
    else
        print("Unknown control action: " .. tostring(action))
    end

    return -1, 0, 0
end

function push_to_buffer(timestamp, record)
    table.insert(log_buffer, {ts = timestamp, rec = record})
    if #log_buffer > BUFFER_LIMIT then
        table.remove(log_buffer, 1)
    end
end

function log_filter(tag, timestamp, record)
    local state = read_state()

    push_to_buffer(timestamp, record)

    if not state.logging_enabled then
        return -1, 0, 0
    end

    if state.logs_processed >= state.max_logs or #log_buffer == 0 then
        state.logging_enabled = false
        state.logs_processed = 0
        write_state(state)
        print("Reached max_logs or buffer empty. Logging auto-disabled.")
        return -1, 0, 0
    end

    local item = table.remove(log_buffer, 1)
    state.logs_processed = state.logs_processed + 1

    if state.logs_processed >= state.max_logs then
        state.logging_enabled = false
        print("Max logs reached: disabling logging.")
    end

    write_state(state)
    return 0, item.ts, item.rec
end
