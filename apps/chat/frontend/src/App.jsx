import React, { useState } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Sidebar from "./Components/Sidebar/Sidebar";
import Main from "./Components/Main/Main";
import Upload from "./Components/Main/Upload";
import "./App.css";
import { ContextProvider } from "./Context/Context";

const App = () => {
  const [sidebarExpanded, setSidebarExpanded] = useState(true);

  return (
    <ContextProvider>
      <Router>
        <div className={`app-container ${sidebarExpanded ? "sidebar-expanded" : "sidebar-collapsed"}`}>
          <aside className="sidebar-container">
            <Sidebar sidebarExpanded={sidebarExpanded} setSidebarExpanded={setSidebarExpanded} />
          </aside>
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Main />} />
              <Route path="/upload" element={<Upload />} />
            </Routes>
          </main>
        </div>
      </Router>
    </ContextProvider>
  );
};

export default App;
