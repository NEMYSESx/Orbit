import React, { useContext, useEffect, useState } from "react";
import "./Sidebar.css";
import { assets } from "../../assets/assets";
import { Context } from "../../Context/Context";

const Sidebar = () => {
  const {
    setUpdateSidebar2,
    updateSidebar,
    setActiveConversationId,
    activeConversationId,
    createNewChat,
    stopReply,
  } = useContext(Context);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [conversations, setConversations] = useState([]);
  const [showDeletePopup, setShowDeletePopup] = useState(false);

  useEffect(() => {
    const fetchTitle = async () => {
      try {
        const response = await fetch(
          "http://localhost:8080/conversation/sidebar"
        );
        const result = await response.json();
        setConversations(Array.isArray(result) ? result : []);
      } catch (error) {
        console.error("Error fetching conversations:", error);
        setConversations([]);
      }
    };
    fetchTitle();
  }, [activeConversationId, updateSidebar]);

  const handleChatMenuClicked = () => {
    setShowDeletePopup(true);
  };

  const confirmDeleteChat = async () => {
    setShowDeletePopup(false);
    await fetch(`http://localhost:8080/conversation/${activeConversationId}`, {
      method: "DELETE",
    });
    setUpdateSidebar2((prev) => !prev);
    setActiveConversationId(null);
  };

  const handleMenuIconClicked = () => {
    setSidebarExpanded((prev) => !prev);
  };

  return (
    <div className={`sidebar ${sidebarExpanded ? "expanded" : "collapsed"}`}>
      {showDeletePopup && (
        <div className="popup-overlay">
          <div className="popup-box">
            <p>Are you sure you want to delete this chat?</p>
            <div className="popup-buttons">
              <button onClick={confirmDeleteChat}>Delete</button>
              <button onClick={() => setShowDeletePopup(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      <div className="top">
        <div className="flex items-center justify-between mb-4">
          <svg
            onClick={handleMenuIconClicked}
            width="24"
            height="24"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
            className="menu-icon cursor-pointer"
          >
            <path
              fillRule="evenodd"
              clipRule="evenodd"
              d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3Z"
              fill="currentColor"
            />
          </svg>
        </div>

        <div
          className={`${sidebarExpanded ? "newchat_expanded" : ""} new_chat`}
          onClick={createNewChat}
        >
          {!sidebarExpanded && <img src={assets.plus_icon} alt="New Chat" />}
          {sidebarExpanded && <p>New Chat</p>}
        </div>

        {sidebarExpanded && (
          <div className="recent">
            <p className="recent_title">Recent</p>
            {Array.isArray(conversations) && conversations.map((conv) => (
              <div
                key={conv.sessionId}
                className={`chat-title recent_entry ${
                  activeConversationId === conv.sessionId ? "active" : ""
                }`}
                onClick={() => {
                  activeConversationId !== conv.sessionId && stopReply();
                  setActiveConversationId(conv.sessionId);
                }}
              >
                <p className="chatName">
                  <span>
                    {conv.title
                      ? activeConversationId === conv.sessionId
                        ? conv.title.slice(0, 30)
                        : conv.title.slice(0, 18)
                      : "New Chat"}
                    ...
                  </span>
                  {activeConversationId === conv.sessionId && (
                    <span className="menu" onClick={handleChatMenuClicked}>
                      <img src={assets.deleteBtn} alt="Delete" />
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;