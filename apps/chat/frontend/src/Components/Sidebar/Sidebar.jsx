import React, { useContext, useEffect, useState } from "react";
import "./Sidebar.css";
import { assets } from "../../assets/assets";
import { Context } from "../../Context/Context";

const Sidebar = ({ sidebarExpanded, setSidebarExpanded }) => {
  const backend = import.meta.env.VITE_BACKEND_URL;
  const {
    setUpdateSidebar2,
    updateSidebar,
    setActiveConversationId,
    activeConversationId,
    createNewChat,
    stopReply,
  } = useContext(Context);
  const [conversations, setConversations] = useState([]);
  const [showDeletePopup, setShowDeletePopup] = useState(false);

  useEffect(() => {
    const fetchTitle = async () => {
      try {
        const response = await fetch(`${backend}/conversation/sidebar`);
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
    await fetch(`${backend}/conversation/${activeConversationId}`, {
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
        <div >
          <img className="menu-icon cursor-pointer" src={assets.expand} alt="" onClick={handleMenuIconClicked}/>
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
            {Array.isArray(conversations) &&
              conversations.map((conv) => (
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
