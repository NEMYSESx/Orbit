
function parse_log(tag, timestamp, record)
    local log_message = record["log"] or record["message"] or ""
    
    if log_message == "" then
        return 0, timestamp, record
    end
    
    local parsed_record = {}
    for k, v in pairs(record) do
        parsed_record[k] = v
    end
    
    local parsed_data = nil
    
    parsed_data = parse_json_log(log_message)
    if parsed_data then
        for k, v in pairs(parsed_data) do
            parsed_record[k] = v
        end
        parsed_record["log_format"] = "json"
        return 1, timestamp, parsed_record
    end
    
    parsed_data = parse_access_log(log_message)
    if parsed_data then
        for k, v in pairs(parsed_data) do
            parsed_record[k] = v
        end
        parsed_record["log_format"] = "access_log"
        return 1, timestamp, parsed_record
    end
    
    parsed_data = parse_syslog(log_message)
    if parsed_data then
        for k, v in pairs(parsed_data) do
            parsed_record[k] = v
        end
        parsed_record["log_format"] = "syslog"
        return 1, timestamp, parsed_record
    end
    
    parsed_data = parse_app_log(log_message)
    if parsed_data then
        for k, v in pairs(parsed_data) do
            parsed_record[k] = v
        end
        parsed_record["log_format"] = "application"
        return 1, timestamp, parsed_record
    end
    
    parsed_record["log_format"] = "unknown"
    parsed_record["original_message"] = log_message
    parsed_record["parsed"] = false
    
    return 1, timestamp, parsed_record
end

function parse_json_log(message)
    if string.match(message, "^%s*{.*}%s*$") then
        local success, result = pcall(function()
            if string.find(message, '"level"') and string.find(message, '"message"') then
                local level = string.match(message, '"level"%s*:%s*"([^"]*)"')
                local msg = string.match(message, '"message"%s*:%s*"([^"]*)"')
                local timestamp_json = string.match(message, '"timestamp"%s*:%s*"([^"]*)"')
                
                return {
                    level = level,
                    message = msg,
                    timestamp_json = timestamp_json,
                    parsed = true
                }
            end
            return nil
        end)
        
        if success and result then
            return result
        end
    end
    return nil
end

function parse_access_log(message)
    local ip, timestamp_str, method, path, protocol, status, size = string.match(message, 
        '([%d%.]+)%s+%-%s+%-%s+%[([^%]]+)%]%s+"(%w+)%s+([^%s]+)%s+([^"]+)"%s+(%d+)%s+(%d+)')
    
    if ip then
        return {
            client_ip = ip,
            access_timestamp = timestamp_str,
            http_method = method,
            request_path = path,
            http_protocol = protocol,
            status_code = tonumber(status),
            response_size = tonumber(size),
            parsed = true
        }
    end
    
    ip, timestamp_str, method, path, status, size = string.match(message,
        '([%d%.]+)%s+.-"%s*(%w+)%s+([^%s]+).-"%s+(%d+)%s+(%d+)')
    
    if ip then
        return {
            client_ip = ip,
            http_method = method,
            request_path = path,
            status_code = tonumber(status),
            response_size = tonumber(size),
            parsed = true
        }
    end
    
    return nil
end

function parse_syslog(message)
    local priority, month, day, time, hostname, tag, msg = string.match(message,
        '<(%d+)>(%w+)%s+(%d+)%s+([%d:]+)%s+([^%s]+)%s+([^:]+):%s*(.*)')
    
    if priority then
        return {
            syslog_priority = tonumber(priority),
            syslog_month = month,
            syslog_day = tonumber(day),
            syslog_time = time,
            hostname = hostname,
            syslog_tag = tag,
            syslog_message = msg,
            parsed = true
        }
    end
    
    month, day, time, hostname, msg = string.match(message,
        '(%w+)%s+(%d+)%s+([%d:]+)%s+([^%s]+)%s+(.*)')
    
    if month then
        return {
            syslog_month = month,
            syslog_day = tonumber(day),
            syslog_time = time,
            hostname = hostname,
            syslog_message = msg,
            parsed = true
        }
    end
    
    return nil
end

function parse_app_log(message)
    local date, time, level, msg = string.match(message,
        '(%d%d%d%d%-%d%d%-%d%d)%s+([%d:]+)%s+%[([^%]]+)%]%s*(.*)')
    
    if date and level then
        return {
            app_date = date,
            app_time = time,
            log_level = level,
            app_message = msg,
            parsed = true
        }
    end
    
    local datetime, level, msg = string.match(message,
        '%[([^%]]+)%]%s+([^:]+):%s*(.*)')
    
    if datetime and level then
        return {
            app_datetime = datetime,
            log_level = level,
            app_message = msg,
            parsed = true
        }
    end
    
    level, msg = string.match(message, '^([A-Z]+):%s*(.*)')
    
    if level then
        return {
            log_level = level,
            app_message = msg,
            parsed = true
        }
    end
    
    return nil
end

function extract_key_values(message)
    local kv_pairs = {}
    
    for key, value in string.gmatch(message, '([%w_]+)=([^%s]+)') do
        kv_pairs[key] = value
    end
    
    for key, value in string.gmatch(message, '([%w_]+)="([^"]*)"') do
        kv_pairs[key] = value
    end
    
    return kv_pairs
end

function cb_parse(tag, timestamp, record)
    return parse_log(tag, timestamp, record)
end