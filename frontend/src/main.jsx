import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import AdminPage from "./AdminPage.jsx";
import "./index.css";

// The owner's dashboard lives at /admin (it asks for the admin key); everything else is the app.
const isAdmin = window.location.pathname.replace(/\/+$/, "") === "/admin";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>{isAdmin ? <AdminPage /> : <App />}</React.StrictMode>
);
