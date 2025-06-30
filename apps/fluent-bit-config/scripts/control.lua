-- Fluent Bit Lua script for controlled log ingestion
-- Only ingest last 100 logs when user toggles ON from frontend

-- Option 1: Use /tmp (most common)
local STATE_FILE = "/tmp/fluent_bit_state.txt"

-- Option 2: Use a custom directory (uncomment if needed)
-- local STATE_FILE = "/var/lib/fluent-bit/state.txt"

-- Option 3: Use relative path (uncomment if needed)
-- local STATE_FILE = "./fluent_bit_state.txt"

-- Helper function to read state from file with better error handling
-- This will create the state file if it doesn't exist
function read_state()
    local file = io.open(STATE_FILE, "r")
    if not file then
        -- Create default state file if it doesn't exist
        local default_state = {
            logging_enabled = false,
            logs_processed = 0,
            max_logs = 100
        }
        write_state(default_state)
        print("🏁 State file created with default values: logging disabled")
        return default_state
    end
    
    local content = file:read("*all")
    file:close()
    
    if content and content ~= "" then
        local state = {
            logging_enabled = false,
            logs_processed = 0,
            max_logs = 100
        }
        
        for line in content:gmatch("[^\r\n]+") do
            local key, value = line:match("([^=]+)=([^=]+)")
            if key and value then
                key = key:gsub("^%s*(.-)%s*$", "%1") -- trim whitespace
                value = value:gsub("^%s*(.-)%s*$", "%1") -- trim whitespace
                
                if key == "logging_enabled" then
                    state[key] = (value == "true")
                elseif key == "logs_processed" or key == "max_logs" then
                    state[key] = tonumber(value) or state[key]
                end
            end
        end
        return state
    end
    
    -- Return default state if content is empty
    return {
        logging_enabled = false,
        logs_processed = 0,
        max_logs = 100
    }
end

-- Helper function to write state to file atomically
function write_state(state)
    local temp_file = STATE_FILE .. ".tmp"
    local file = io.open(temp_file, "w")
    if file then
        file:write("logging_enabled=" .. tostring(state.logging_enabled) .. "\n")
        file:write("logs_processed=" .. tostring(state.logs_processed) .. "\n")
        file:write("max_logs=" .. tostring(state.max_logs) .. "\n")
        file:close()
        
        -- Atomic move (on most Unix systems)
        os.rename(temp_file, STATE_FILE)
        return true
    end
    return false
end

-- Initialize state file - called once at startup
-- Only initialize if state file doesn't exist to avoid overwriting
function init()
    -- Check if state file already exists
    local file = io.open(STATE_FILE, "r")
    if file then
        file:close()
        print("🏁 State file exists, skipping initialization")
        return
    end
    
    -- Only create initial state if file doesn't exist
    local initial_state = {
        logging_enabled = false,
        logs_processed = 0,
        max_logs = 100
    }
    
    if write_state(initial_state) then
        print("🏁 State initialized: logging disabled")
    else
        print("🏁 ❌ Failed to initialize state file!")
    end
end

-- Control handler for enable/disable commands
function control_handler(tag, timestamp, record)
    print("🚀 === CONTROL HANDLER CALLED ===")
    print("🔧 Tag: " .. tostring(tag))
    print("🔧 Timestamp: " .. tostring(timestamp))
    
    -- Debug: print all record fields
    if type(record) == "table" then
        print("🔧 Record contents:")
        for key, value in pairs(record) do
            print("  " .. tostring(key) .. " = " .. tostring(value))
        end
    end
    
    -- Read current state
    local state = read_state()
    print("🔧 Current state before action: enabled=" .. tostring(state.logging_enabled) .. 
          ", processed=" .. state.logs_processed .. "/" .. state.max_logs)
    
    -- Handle control messages
    local action = record["action"]
    if action then
        print("🔧 Action found: " .. tostring(action))
        
        if action == "enable" then
            state.logging_enabled = true
            state.logs_processed = 0  -- Reset counter when enabling
            
            if record["max_logs"] then
                state.max_logs = tonumber(record["max_logs"]) or 100
            end
            
            if write_state(state) then
                print("🟢 ✅ LOGGING ENABLED via HTTP control (max: " .. state.max_logs .. " logs)")
            else
                print("🟢 ❌ LOGGING ENABLED but failed to write state!")
            end
            
        elseif action == "disable" then
            state.logging_enabled = false
            state.logs_processed = 0
            
            if write_state(state) then
                print("🔴 ❌ LOGGING DISABLED via HTTP control")
            else
                print("🔴 ❌ LOGGING DISABLED but failed to write state!")
            end
            
        else
            print("🔧 Unknown action: " .. tostring(action))
        end
    else
        print("🔧 ❌ No 'action' field found in record!")
    end
    
    -- Re-read state to confirm
    local final_state = read_state()
    print("🔧 Final logging_enabled state: " .. tostring(final_state.logging_enabled))
    print("🚀 === CONTROL HANDLER END ===")
    
    -- Drop control messages (don't forward them to output)
    return -1, 0, 0
end

-- Log filter for actual log processing
function log_filter(tag, timestamp, record)
    print("📋 === LOG FILTER CALLED ===")
    print("📋 Tag: " .. tostring(tag))
    
    -- Read current state
    local state = read_state()
    
    print("📋 Current logging_enabled: " .. tostring(state.logging_enabled))
    print("📋 Current logs_processed: " .. state.logs_processed .. "/" .. state.max_logs)
    
    -- If logging is disabled, drop all logs
    if not state.logging_enabled then
        print("📋 ❌ Dropping log - logging disabled")
        return -1, 0, 0
    end
    
    -- If we've processed enough logs, disable and drop
    if state.logs_processed >= state.max_logs then
        state.logging_enabled = false
        state.logs_processed = 0  -- Reset for next enable cycle
        
        if write_state(state) then
            print("📋 🔴 AUTO-DISABLED - processed " .. state.max_logs .. " logs")
        else
            print("📋 🔴 AUTO-DISABLED but failed to write state!")
        end
        return -1, 0, 0
    end
    
    -- Increment counter and allow log
    state.logs_processed = state.logs_processed + 1
    
    if write_state(state) then
        print("📋 ✅ PROCESSING log " .. state.logs_processed .. "/" .. state.max_logs .. " (tag: " .. tag .. ")")
    else
        print("📋 ✅ PROCESSING log " .. state.logs_processed .. "/" .. state.max_logs .. " (tag: " .. tag .. ") - state write failed!")
    end
    
    return 0, timestamp, record
end