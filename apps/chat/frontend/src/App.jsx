import React from 'react';
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Sidebar from './Components/Sidebar/Sidebar';
import Main from './Components/Main/Main';
import RaiseTicket from "./Components/RaiseTicket/RaiseTicket";


const App = () => {
  return (
    <Router>
      <Routes>
        <Route
          path="/"
          element={
            <>
              <Main />
              <Sidebar />
            </>
          }
        />
        <Route
          path="/raise-ticket"
          element={<RaiseTicket />}
        />
      </Routes>
    </Router>
  );
};

export default App;