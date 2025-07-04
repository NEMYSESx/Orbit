import React, { useContext, useEffect, useRef, useState } from "react";
import "./Main.css";
import { assets } from "../../assets/assets";
import Card from "./Card";
import { Context } from "../../Context/Context";

const Main = () => {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [searchInLogs, setSearchInLogs] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speakingIndex, setSpeakingIndex] = useState(null);
  const recognitionRef = useRef(null);
  const synthRef = useRef(window.speechSynthesis);

  const [file, setFile] = useState(null);
  const {
    onSent,
    loading,
    setInput,
    input,
    conversation,
    allowSending,
    stopReply,
    stopIcon,
  } = useContext(Context);

  const chatEndRef = useRef(null);

  const scrollToBottom = () =>
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });

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
      } else {
        document.documentElement.classList.remove("dark-mode");
      }
      return newMode;
    });
  };

  const handleSend = () => {
    if (input.trim() && allowSending) {
      onSent(input, file, { searchInLogs });
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

    setIsToggling(true);
    const newState = !searchInLogs;

    try {
      console.log(`Attempting to set Fluent Bit to: ${newState}`);

      const response = await fetch("http://localhost:8080/api/fluent/toggle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          enabled: newState,
        }),
      });

      console.log(`Response status: ${response.status}`);

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ detail: "Unknown error" }));
        throw new Error(
          `HTTP error! status: ${response.status} - ${errorData.detail}`
        );
      }

      const result = await response.json();
      console.log("API Response:", result);

      if (result.success) {
        setSearchInLogs(newState);
        if (newState) {
          setIsIngesting(true);
          pollIngestionStatus();
        }
        console.log(`Fluent Bit successfully set to: ${newState}`);
      } else {
        throw new Error(result.message || "API returned success: false");
      }
    } catch (error) {
      console.error("Error toggling Fluent Bit:", error);
      alert(`Failed to toggle log search: ${error.message}`);
    } finally {
      setIsToggling(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Function to get the latest bot message
  const getLatestBotMessage = () => {
    if (!conversation.messages) return "";
    const botMessages = conversation.messages.filter(
      (msg) => msg.type === "bot"
    );
    if (botMessages.length === 0) return "";
    return botMessages[botMessages.length - 1].text.replace(/<[^>]+>/g, ""); // Remove HTML tags
  };

  // Speak handler for a specific message
  const handleSpeak = (text, idx) => {
    if (!text) return;
    if (synthRef.current.speaking) {
      synthRef.current.cancel();
    }
    const utter = new window.SpeechSynthesisUtterance(text);
    utter.onend = () => setSpeakingIndex(null);
    synthRef.current.speak(utter);
    setSpeakingIndex(idx);
  };

  // Stop handler for a specific message
  const handleStopSpeak = () => {
    synthRef.current.cancel();
    setSpeakingIndex(null);
  };

  return (
    <div className={`main`}>
      {isIngesting && (
        <div className="ingestion_overlay">
          <div className="spinner"></div>
          <p>Ingesting logs... Please wait</p>
        </div>
      )}

      <div className="nav">
        <p>Orbit</p>
        <div className="nav_right">
          <img
            className={isDarkMode ? "light_mode_icon" : "dark_mode_icon"}
            src={isDarkMode ? assets.light_mode : assets.night_mode}
            onClick={toggleDarkMode}
            alt={isDarkMode ? "Light Mode" : "Dark Mode"}
          />
          <img src={assets.user_icon} alt="User" />
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
            <div className="cards">{/* <Card /> here if needed */}</div>
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
                        <p
                          dangerouslySetInnerHTML={{ __html: message.text }}
                        ></p>
                        {/* Speak/Stop button for each answer */}
                        <button
                          className={`icon_button speak_stop_button`}
                          onClick={
                            speakingIndex === index
                              ? handleStopSpeak
                              : () =>
                                  handleSpeak(
                                    message.text.replace(/<[^>]+>/g, ""),
                                    index
                                  )
                          }
                          disabled={loading || !message.text}
                          title={
                            speakingIndex === index
                              ? "Stop speaking"
                              : "Speak this bot reply"
                          }
                          style={{
                            marginLeft: "8px",
                            marginTop: "8px",
                            background:
                              speakingIndex === index ? "#e74c3c" : "#3498db",
                            color: "#fff",
                            border: "none",
                          }}
                        >
                          {speakingIndex === index ? "Stop" : "Speak"}
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <p>{message.text}</p>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={chatEndRef}></div>
      </div>

      <div
        className={`main_bottom ${file ? "main_bottom_with_file" : ""}`}
        style={{ marginLeft: "120px" }}
      >
        <div className="search_box">
          <div className="search_header">
            <div className="toggle_container">
              <span className="toggle_label">Search in Logs</span>
              <button
                className={`toggle_switch ${searchInLogs ? "active" : ""} ${
                  isToggling ? "loading" : ""
                }`}
                onClick={toggleFluentBit}
                disabled={isToggling}
                title={isToggling ? "Updating..." : "Toggle log search"}
              >
                <div className="toggle_slider"></div>
              </button>
            </div>
          </div>

          {file && (
            <div className="file_container">
              <img className="new_file" src={assets.file} alt="File" />
              <p className="file_name">{file.name}</p>
              <img
                src={assets.cross}
                onClick={() => setFile(null)}
                alt="Remove file"
                style={{ cursor: "pointer" }}
              />
            </div>
          )}

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
                className={`icon_button mic_button ${
                  isListening ? "listening" : ""
                }`}
                onClick={isListening ? stopListening : startListening}
                title={isListening ? "Stop Listening" : "Voice Input"}
                disabled={loading}
              >
                <img
                  src={isListening ? assets.mic_active_icon : assets.mic_icon}
                  className="utility_icon"
                  alt="Microphone"
                />
              </button>

              <input
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                style={{ display: "none" }}
                id="fileUpload"
                accept="*/*"
              />
              <label
                className="icon_button file_button"
                htmlFor="fileUpload"
                title="Upload File"
              >
                <img
                  className="file_icon utility_icon"
                  src={assets.add_file}
                  alt="Upload file"
                />
              </label>

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
                <img
                  src={stopIcon ? assets.stop_button : assets.send_icon}
                  alt={stopIcon ? "Stop" : "Send"}
                  className="utility_icon"
                />
              </button>
            </div>
          </div>

          {searchInLogs && (
            <div className="search_status">
              <div className="status_indicator"></div>
              <span>Searching in logs</span>
            </div>
          )}
        </div>
      </div>

      <div className="transparent"></div>
    </div>
  );
};

export default Main;
