import React, { useState } from "react";
import "./RaiseTicket.css";

const RaiseTicket = ({ onClose}) => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [query, setQuery] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    // Here you can add code to send data to your backend/admin system
    alert(`Ticket Raised!\nName: ${name}\nEmail: ${email}\nQuery: ${query}`);
    // Optionally, clear form or navigate back to chat
    setName("");
    setEmail("");
    setQuery("");
    if (onClose) { // Close the form if onClose prop is provided
      onClose();
    }
  };

  const handleCancel = () => {
    // Optionally, confirm with the user before canceling
    if (window.confirm("Are you sure you want to cancel? Your unsaved changes will be lost.")) {
      setName("");
      setEmail("");
      setQuery("");
      if (onClose) { // Close the form if onClose prop is provided
        onClose();
      }
    }
  };

  return (
    <div className="raise-ticket-container">
    {/* <div style={{ maxWidth: 400, margin: "auto", padding: 20 }}> */}
      <h2>Raise a Ticket</h2>
      <form onSubmit={handleSubmit} className="ticket-form">
        <label>
          Name:<br />
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <br />
        <label>
          Email:<br />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <br />
        <label>
          Query:<br />
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
            rows={5}
          />
        </label>
        <br />
        <button type="submit">Submit Ticket</button>
        <br />
        <button type="cancel">Cancel Ticket</button>
      </form>
    </div>
  );
};

export default RaiseTicket;
