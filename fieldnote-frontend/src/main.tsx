
  import { createRoot } from "react-dom/client";
  import App from "./app/App";
  import { AuthProvider } from "./auth/AuthProvider";
  import "./styles/index.css";

  createRoot(document.getElementById("root")!).render(<AuthProvider><App /></AuthProvider>);
  
