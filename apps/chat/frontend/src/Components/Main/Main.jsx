import React, { useContext, useEffect, useRef, useState } from "react";
import "./Main.css";
import { assets } from "../../assets/assets";
import Card from "./Card";

import { Link, useNavigate } from "react-router";
import { Context } from "../../Context/Context";
import { Copy, RefreshCw } from "lucide-react";


const Main = () => {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const stored = localStorage.getItem("theme");
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  const [isListening, setIsListening] = useState(false);
  const [searchInLogs, setSearchInLogs] = useState(false);
  const [resultCount, setResultCount] = useState(10);
  const [isToggling, setIsToggling] = useState(false);
  const recognitionRef = useRef(null);
  const [lastUserInput, setLastUserInput] = useState("");

  const [file, setFile] = useState(null);
  const { onSent, loading, setInput, input, conversation, allowSending, stopReply, stopIcon, regenerateResponse, isThinking} = useContext(Context);

  const chatEndRef = useRef(null);
  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: "smooth" });

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add("dark-mode");
    } else {
      document.documentElement.classList.remove("dark-mode");
    }

    if ("webkitSpeechRecognition" in window) {
      const SpeechRecognition = window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = false;
      recognitionRef.current.lang = "en-US";

      recognitionRef.current.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput((prevInput) => prevInput + transcript);
        setIsListening(false);
      };

      recognitionRef.current.onerror = () => {
        setIsListening(false);
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };
    }
  }, [isDarkMode]);

  const startListening = () => {
    if (recognitionRef.current) {
      setIsListening(true);
      recognitionRef.current.start();
    }
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      setIsListening(false);
      recognitionRef.current.stop();
    }
  };

  
  const toggleDarkMode = () => {
    setIsDarkMode((prevMode) => {
      const newMode = !prevMode;
      if (newMode) {
        document.documentElement.classList.add("dark-mode");
        localStorage.setItem("theme", "dark");
      } else {
        document.documentElement.classList.remove("dark-mode");
        localStorage.setItem("theme", "light");
      }
      return newMode;
    });
  };

  const handleSend = () => {
    if (input.trim() && allowSending) {
      onSent(input, file, { searchInLogs, resultCount });
      setFile(null);
      scrollToBottom();
    }
  };

  const pollIngestionStatus = async () => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch("http://localhost:8080/api/fluent/status");
        const data = await res.json();

        if (!data.ingesting) {
          clearInterval(interval);
          setIsIngesting(false);
          console.log("✅ Ingestion completed");
        }
      } catch (err) {
        console.error("Polling error:", err);
        clearInterval(interval);
        setIsIngesting(false);
      }
    }, 1500);
  };


  const toggleFluentBit = async () => {
    if (isToggling) return;

    const previousState = searchInLogs;
    setIsToggling(true);

    try {
      setSearchInLogs(!searchInLogs);

      const response = await fetch("http://localhost:8080/api/fluent/toggle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          enabled: !previousState,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();

      if (!result.success) {
        setSearchInLogs(previousState);
        console.error(
          "Failed to toggle Fluent Bit:",
          result.message || "Unknown error"
        );
      } else {
        console.log("Fluent Bit toggled successfully:", result.message);
      }
    } catch (error) {
      setSearchInLogs(previousState);
      console.error("Error toggling Fluent Bit:", error);
    } finally {
      setIsToggling(false);
    }
  };

  // const handleResultCountChange = (e) => {
  //   const value = parseInt(e.target.value) || 1;
  //   setResultCount(Math.max(1, Math.min(100, value)));
  // };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`main`}>
      <div className="nav">
        <p>Orbit</p>
        <div className="nav_right">
          <img
            className={isDarkMode ? "light_mode_icon" : "dark_mode_icon"}
            src={isDarkMode ? assets.light_mode : assets.night_mode}
            onClick={toggleDarkMode}
            alt={isDarkMode ? "Light Mode" : "Dark Mode"}
          />
        </div>
      </div>

      <div className="main_container">
        {!conversation.messages || conversation.messages.length === 0 ? (
          <>
            <div className="greet">
              <p>
                <span>Hello, Dev</span>
              </p>
              <p className="greetMsg">How can I help you today?</p>
            </div>
            {/* <div className="cards"><Card /> here if needed</div> */}
          </>
        ) : (
          conversation.messages.map((message, index) => (
            <div key={index} className="result">
              <div className={`result_title ${message.type}`}>
                {message.type === "bot" ? (
                  <div className={`result_data`}>
                    {index === conversation.messages.length - 1 && loading ? (
                      <div className="loader">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    ) : (
                      <div className="hello">
                        <p dangerouslySetInnerHTML={{ __html: message.text }}></p>
                        <div className="chat-utils">
                          <Copy
                            size={18}
                            className="icon-btn"
                            onClick={() => {
                              const tempElement = document.createElement("div");
                              tempElement.innerHTML = message.text;
                              const plainText = tempElement.textContent || tempElement.innerText || "";
                              navigator.clipboard.writeText(plainText);
                            }}
                            title="Copy"
                          />
                          <RefreshCw
                            size={18}
                            className="icon-btn"
                            onClick={() => regenerateResponse(lastUserInput)}
                            title="Regenerate"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="user_msg">
                    <p>{message.text}</p>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={chatEndRef}></div>
      </div>

      <div className={`main_bottom ${file ? "main_bottom_with_file" : ""}`}>
        <div className="search_box">
          {/* Search Options Header */}
          <div className="search_header">
            <div className="toggle_container">
              <span className="toggle_label">Search in Logs</span>
              <button
                className={`toggle_switch ${searchInLogs ? "active" : ""} ${isToggling ? "loading" : ""}`}
                onClick={toggleFluentBit}
                disabled={isToggling}
                title={isToggling ? "Updating..." : "Toggle log search"}
              >
                <div className="toggle_slider"></div>
              </button>
            </div>
            {/* <div className="result_count_container">
              <label className="input_label">No of logs</label>
              <input
                type="number"
                className="result_count_input"
                value={resultCount}
                onChange={handleResultCountChange}
                min="1"
                max="100"
                placeholder="10"
              />
            </div> */}
          </div>

          {/* File Container */}
          {file && (
            <div className="file_container">
              <img className="new_file" src={assets.file} alt="File" />
              <p className="file_name">{file.name}</p>
              <img src={assets.cross} onClick={() => setFile(null)} alt="Remove file" style={{ cursor: "pointer" }} />
            </div>
          )}

          {/* Main Input Row */}
          <div className="input_row">
            <div className="main_input_container">
              <input
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                value={input}
                type="text"
                placeholder="Ask anything..."
                className="main_text_input"
                disabled={loading}
              />
            </div>

            <div className="action_buttons">
              <button
                className={`icon_button mic_button ${isListening ? "listening" : ""}`}
                onClick={isListening ? stopListening : startListening}
                title={isListening ? "Stop Listening" : "Voice Input"}
                disabled={loading}
              >
                <img src={isListening ? assets.mic_active_icon : assets.mic_icon} className="utility_icon" alt="Microphone" />
              </button>

              <Link className="icon_button file_button" to={"/upload"} title="upload file">
                <img className="file_icon utility_icon" src={assets.add_file} alt="Upload file" />
              </Link>

              <button
                className="icon_button send_button primary"
                onClick={() => {
                  if (stopIcon) {
                    stopReply();
                  } else {
                    handleSend();
                  }
                }}
                title={stopIcon ? "Stop" : "Send Message"}
                disabled={loading && !stopIcon}
              >
                <img src={stopIcon ? assets.stop_button : assets.send_icon} alt={stopIcon ? "Stop" : "Send"} className="utility_icon" />
              </button>
            </div>
          </div>

          {/* Search Status */}
          {(searchInLogs || resultCount !== 10) && (
            <div className="search_status">
              <div className="status_indicator"></div>
              <span>
                {searchInLogs ? `Searching in logs` : `Regular search`} with{" "}
                {resultCount} result{resultCount !== 1 ? "s" : ""}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="transparent"></div>
    </div>
  );
};

export default Main;
