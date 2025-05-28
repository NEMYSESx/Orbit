import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Sidebar from "./Components/Sidebar/Sidebar";
import Main from "./Components/Main/Main";
import Upload from "./Components/Main/Upload";
import "./App.css";
import { Context, ContextProvider } from "./Context/Context";

const App = () => {
  return (
    <ContextProvider>
      <Router>
        <div className="app-container">
          <aside className="sidebar-container">
            <Sidebar />
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
