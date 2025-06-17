import { createContext, useState, useRef, useEffect } from "react";
import { marked } from "marked";

export const Context = createContext();

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const backendUrl = import.meta.env.VITE_BACKEND_URL;

const generateNewChat = async () => {
  try {
    const response = await fetch(`${backendUrl}/conversation/create`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: "New Chat",
        messages: [],
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error("Error posting to backend:", error);
    return null;
  }
};

// Move session functions outside of component
async function createSession() {
  const apiUrl = import.meta.env.VITE_API_URL;

  try {
    const response = await fetch(`${apiUrl}/sessions/create`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to create session: ${response.status}`);
    }

    const sessionData = await response.json();
    console.log("Session created:", sessionData);
    return sessionData.session_id;
  } catch (error) {
    console.error("Error creating session:", error);
    throw error;
  }
}

async function handleRagQueryWithSession(userPrompt, existingSessionId = null) {
  let session_id = existingSessionId;

  // Create a new session if one doesn't exist
  if (!session_id) {
    try {
      session_id = await createSession();
      console.log("New session created with ID:", session_id);
    } catch (error) {
      console.error("Failed to create session:", error);
      // Optionally continue without session_id or return early
      // return { error: "Failed to create session" };
    }
  }

  console.log("This is my session id", session_id);

  const userPayload = {
    query: userPrompt,
    session_id: session_id,
  };

  let botReply;
  const apiUrl = import.meta.env.VITE_API_URL;
  console.log(apiUrl);

  try {
    const response = await fetch(`${apiUrl}/rag/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(userPayload),
    });

    console.log("Response status:", response.status);

    if (response.ok) {
      const result = await response.json();
      console.log("Raw result object:", result);

      if (result && result.answer) {
        botReply = { response: result.answer };
      } else {
        console.error("Unexpected response structure:", result);
        botReply = {
          response: "Unexpected response format from RAG service",
        };
      }
    } else {
      console.error("Error:", response.statusText);
      botReply = { response: `Error: ${response.statusText}` };
    }
  } catch (error) {
    console.error("Error:", error);
    botReply = { response: `Error: ${error.message}` };
  }

  return {
    session_id: session_id,
    response: botReply,
  };
}

export const ContextProvider = (props) => {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showResult, setShowResult] = useState(false);
  const [allowSending, setAllowSending] = useState(true);
  const [stopIcon, setStopIcon] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);

  const stopReplyRef = useRef(false);

  const [conversation, setConversation] = useState({ messages: [] });
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [updateSidebar, setUpdateSidebar] = useState(true);
  const [updateSidebar2, setUpdateSidebar2] = useState(true);

  const createNewChat = async () => {
    stopReply();
    if (conversation && conversation.title !== "New Chat") {
      const newChat = await generateNewChat();
      if (newChat) {
        setConversation(newChat);
        setActiveConversationId(newChat.sessionId);
        setCurrentSessionId(null); // Reset session ID for new chat
      }
    }
  };

  useEffect(() => {
    const getConvo = async () => {
      try {
        const response = await fetch(`${backendUrl}/conversation/initial`, {
          method: "GET",
        });
        if (response.ok) {
          const result = await response.json();
          if (result) {
            setConversation(result);
            setActiveConversationId(result.sessionId);
          }
        }
      } catch (error) {
        console.error("Error fetching initial conversation:", error);
      }
    };
    getConvo();
  }, [updateSidebar2]);

  useEffect(() => {
    if (!activeConversationId) return;
    const getCurrentConversation = async () => {
      try {
        stopReplyRef.current = true;
        const response = await fetch(
          `${backendUrl}/conversation/active/${activeConversationId}`
        );
        if (response.ok) {
          const result = await response.json();
          if (
            result &&
            conversation &&
            result.sessionId !== conversation.sessionId
          ) {
            setConversation(result);
          }
        }
      } catch (error) {
        console.error("Error fetching current conversation:", error);
      }
    };
    getCurrentConversation();
  }, [activeConversationId]);

  const getSuggestions = async () => {
    try {
      const response = await fetch(`${backendUrl}/suggestions/`);
      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (error) {
      console.error("Error fetching suggestions:", error);
    }
  };

  useEffect(() => {
    getSuggestions();
  }, []);

  const onSent = async (prompt) => {
    const userPrompt = prompt || input;

    setAllowSending(false);
    setLoading(true);
    stopReplyRef.current = false;
    setStopIcon(true);
    setShowResult(true);

    const userMessage = { type: "user", text: userPrompt };
    const botMessage = { type: "bot", text: "..." };

    setConversation((prev) => ({
      ...prev,
      messages: [...(prev?.messages || []), userMessage, botMessage],
    }));

    setInput("");
    console.log(currentSessionId);

    try {
      const result = await handleRagQueryWithSession(
        userPrompt,
        currentSessionId
      );

      if (result.session_id) {
        setCurrentSessionId(result.session_id);
      }

      const botReply = result.response;
      const formattedResponse = marked(
        botReply?.response || "Something went wrong"
      );

      await sleep(1000);

      let currentIndex = 0;

      const typeBotResponse = () => {
        setConversation((prev) => {
          const updatedMessages = [...(prev?.messages || [])];
          const currentText = formattedResponse.slice(0, currentIndex);
          updatedMessages[updatedMessages.length - 1] = {
            type: "bot",
            text: marked(currentText),
          };
          return {
            ...prev,
            messages: updatedMessages,
          };
        });

        currentIndex++;

        if (currentIndex <= formattedResponse.length && !stopReplyRef.current) {
          setTimeout(typeBotResponse, 10);
        } else {
          if (activeConversationId) {
            saveToBackend();
          }
          setLoading(false);
          setStopIcon(false);
          setAllowSending(true);
        }
      };

      typeBotResponse();

      async function saveToBackend() {
        try {
          const response = await fetch(
            `${backendUrl}/conversation/${activeConversationId}`,
            {
              method: "POST",
              headers: {
                "Content-type": "application/json",
              },
              body: JSON.stringify({
                userMsg: userMessage,
                botMsg: { type: "bot", text: formattedResponse },
                prompt: userPrompt,
              }),
            }
          );
          if (response.ok) {
            const result = await response.json();
            console.log("savedddddd", result);
            setUpdateSidebar(!updateSidebar);

            if (conversation && conversation.title === "New Chat") {
              setConversation((prev) => ({
                ...prev,
                title: userPrompt.slice(0, 20),
              }));
            }
          }
        } catch (error) {
          console.error("Error saving to backend:", error);
        }
      }
    } catch (error) {
      console.error("Error in onSent:", error);

      // Handle error in UI
      setConversation((prev) => {
        const updatedMessages = [...(prev?.messages || [])];
        updatedMessages[updatedMessages.length - 1] = {
          type: "bot",
          text: "Sorry, there was an error processing your request.",
        };
        return {
          ...prev,
          messages: updatedMessages,
        };
      });

      setLoading(false);
      setStopIcon(false);
      setAllowSending(true);
    }
  };

  const stopReply = () => {
    stopReplyRef.current = true;
    setLoading(false);
    setAllowSending(true);
    setStopIcon(false);

    setConversation((prev) => {
      const messages = [...(prev?.messages || [])];
      if (messages.length && messages[messages.length - 1].type === "bot") {
        messages[messages.length - 1] = {
          type: "bot",
          text: messages[messages.length - 1].text,
        };
      }
      return {
        ...prev,
        messages,
      };
    });
  };

  return (
    <Context.Provider
      value={{
        conversation,
        setActiveConversationId,
        activeConversationId,
        onSent,
        input,
        setInput,
        loading,
        showResult,
        allowSending,
        stopReply,
        stopIcon,
        suggestions,
        createNewChat,
        updateSidebar,
        setUpdateSidebar,
        updateSidebar2,
        setUpdateSidebar2,
      }}
    >
      {props.children}
    </Context.Provider>
  );
};

export default ContextProvider;
