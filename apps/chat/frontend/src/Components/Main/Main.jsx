import React, { useContext, useRef, useState, useEffect } from "react";
import "./Main.css";
import { assets } from "../../assets/assets";
import Card from "./Card";
import { Context } from "../../Context/Context";
// import { useNavigate } from "react-router-dom";
import RaiseTicket from "../RaiseTicket/RaiseTicket";

const Main = () => {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [file, setFile] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);
  // const navigate = useNavigate();
  const [showRaiseTicket, setShowRaiseTicket] = useState(false);


  const {
    onSent,
    loading,
    setInput,
    input,
    conversation,
    allowSending,
    stopReply,
    stopIcon,
    suggestions,
  } = useContext(Context);

  const cardText = suggestions;
  
  useEffect(() => {
    if (!loading) {
      scrollToBottom();
    }
  }, [conversation.messages, loading]);
    
  const handleCopy = (htmlString, index) => {
    const tempElement = document.createElement("div");
    tempElement.innerHTML = htmlString;
    const textOnly = tempElement.textContent || tempElement.innerText || "";
    navigator.clipboard.writeText(textOnly);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 1500);
  };
  
  const handleRetry = (indexToUpdate) => {
    if (indexToUpdate <= 0) return; 
    const previousUserMessage = conversation.messages[indexToUpdate - 1];
    if (!previousUserMessage || previousUserMessage.type !== "user") {
      console.warn("No valid previous user message to retry.");
      return;
    }

    setInput(previousUserMessage.text);
    onSent(previousUserMessage.text, file, indexToUpdate); // Pass the index to update
    setConversation(prevConvo => {
        const newMessages = [...prevConvo.messages];
        
        if (newMessages[indexToUpdate]) {
            newMessages[indexToUpdate] = {
                ...newMessages[indexToUpdate],
                text: "Retrying...", 
            };
        }
        return { ...prevConvo, messages: newMessages };
    });
  };




  const chatEndRef = useRef(null);
  const scrollToBottom = () =>
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
  return (
    <div className={`main`}>
      <div className="nav">
        <p>Orbit</p>{" "}
        <div className="nav_right">
          {" "}
          <div className="nav_right">
            <img
              className={isDarkMode ? "light_mode_icon" : "dark_mode_icon"}
              src={isDarkMode ? assets.light_mode : assets.night_mode}
              onClick={toggleDarkMode}
              alt={isDarkMode ? "Light Mode" : "Dark Mode"}
            />
            <img src={assets.user_icon} alt="User" />
          </div>
        </div>{" "}
      </div>
      <div className="main_container">
        {showRaiseTicket ? (
          <RaiseTicket onClose={() => setShowRaiseTicket(false)} />
        ) : !conversation.messages || conversation.messages.length === 0 ? (
          <>
            <div className="greet">
              <p>
                <span>Hello, Dev</span>
              </p>
              <p className="greetMsg">How can I help you today?</p>
            </div>
            <div className="cards">
              {cardText.map((text, i) => (
                <Card key={i} cardText={text} index={i} />
              ))}
            </div>
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
                      <>
                        <div className="bot-message-block">
                          <div className="hello">
                            <p
                              dangerouslySetInnerHTML={{ __html: message.text }}
                            ></p>
                          </div>
                          <div className="message-footer">
                            <button onClick={() => handleCopy(message.text, index)}>
                              {copiedIndex === index ? "✅ Copied!" : "Copy"}
                            </button>
                            <button onClick={() => handleRetry(index)}>Retry</button>
                            {/* <button onClick={() => navigate("/raise-ticket")}>Raise Ticket</button> */}
                            <button onClick={() => setShowRaiseTicket(true)}>Raise Ticket</button>
                            

                          </div>
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <>
                    <p>{message.text}</p>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>
      {!showRaiseTicket && (
      <div className={`main_bottom ${file && 'main_bottom_with_file'}`}>
        <div className="search_box">
          {file &&(
            <div className="file_container">
              <img className="new_file" src={assets.file} alt="" />
              <p className="file_name">{file.name}</p>
              <img src={assets.cross}  onClick={() => setFile(null)} />
            </div>
          )}
          <div className="tempo">
          <input
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && input.trim() && allowSending) {
                onSent(input, file);
                setFile(null)
                scrollToBottom();
              }
            }}
            value={input}
            type="text"
            placeholder="Ask anything"
          />
          <div>
            <input
              type="file"
              onChange={(e) => {
                setFile(e.target.files[0]);
              }}
              style={{ display: "none" }}
              id="fileUpload"
            />
            <img src={assets.mic_icon} className="utility_icon" alt="" />
            <label className="file_label" htmlFor="fileUpload">
              <img className="file_icon utility_icon" src={assets.add_file} alt="" />

            </label>
            <img
              onClick={() => {
                if (stopIcon) {
                  stopReply();
                } else if (input.trim() && allowSending) {
                  onSent(input, file);
                  setFile(null)
                  scrollToBottom();
                }
              }}
              src={stopIcon ? assets.stop_button : assets.send_icon}
              alt="" className="utility_icon"
            />
          </div>
        </div>
      </div>
    </div>
    )}
      // <div className="transparent"></div>
      // <div ref={chatEndRef}></div>
  </div>
  );
};

export default Main;
