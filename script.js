const chatbotToggler = document.querySelector(".chatbot-toggler");
const closeBtn = document.querySelector(".close-btn");
const chatbox = document.querySelector(".chatbox");
const chatInput = document.querySelector(".chat-input textarea");
const sendChatBtn = document.querySelector(".chat-input span");

let userMessage = null; // Variable to store user's message
const inputInitHeight = chatInput.scrollHeight;

const createChatLi = (message, className) => {
    // Create a chat <li> element with passed message and className
    const chatLi = document.createElement("li");
    chatLi.classList.add("chat", `${className}`);
    let chatContent = className === "outgoing" ? `<p></p>` : `<span class="material-symbols-outlined">smart_toy</span><p></p>`;
    chatLi.innerHTML = chatContent;
    chatLi.querySelector("p").textContent = message;
    return chatLi; // return chat <li> element
}

const MAX_REQUESTS_PER_MINUTE = 58; // Adjust based on your subscription level
let lastRequestTimestamp = 0;

const generateResponse = (chatElement) => {
    const messageElement = chatElement.querySelector("p");

    const now = Date.now();
    const timeSinceLastRequest = now - lastRequestTimestamp;

    if (timeSinceLastRequest < 60000 / MAX_REQUESTS_PER_MINUTE) {
        setTimeout(() => generateResponse(chatElement), 60000 / MAX_REQUESTS_PER_MINUTE - timeSinceLastRequest);
        return;
    }

    lastRequestTimestamp = now;

    userMessage = messageElement.textContent.trim(); // Get user's message from chatElement

    fetch("http://localhost:5000/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            message: userMessage,
        }),
        timeout: 10000, // Adjust the timeout value as needed (in milliseconds)
    })
    .then((res) => res.json())
    .then((data) => {
        console.log(data);
        const chatbotReply = data.reply;
        
        // Display the chatbot's reply in the chatbox
        const chatbotResponseLi = createChatLi(chatbotReply, "incoming");
        chatbox.appendChild(chatbotResponseLi);
        chatbox.scrollTo(0, chatbox.scrollHeight);
    })
    .catch(() => {
        messageElement.classList.add("error");
        messageElement.textContent = "Oops! Something went wrong.";
    })
    .finally(() => chatbox.scrollTo(0, chatbox.scrollHeight));
}

const handleChat = () => {
  userMessage = chatInput.value.trim(); // Get user entered message and remove extra whitespace
  if (!userMessage) return;

  // Clear the input textarea and set its height to default
  chatInput.value = "";
  chatInput.style.height = `${inputInitHeight}px`;

  // Append the user's message to the chatbox
  chatbox.appendChild(createChatLi(userMessage, "outgoing"));
  chatbox.scrollTo(0, chatbox.scrollHeight);

  setTimeout(() => {
      // Display "Thinking..." message while waiting for the response
      const incomingChatLi = createChatLi("Here's my response: ", "incoming");
      chatbox.appendChild(incomingChatLi);
      chatbox.scrollTo(0, chatbox.scrollHeight);

      // Send a POST request to the Flask server
      fetch("http://localhost:5000/chat", { // Replace with the correct URL
          method: "POST",
          headers: {
              "Content-Type": "application/json",
          },
          body: JSON.stringify({
              message: userMessage,
          }),
      })
      .then((res) => res.json())
      .then((data) => {
          console.log(data);
          const chatbotReply = data.reply;

          // Display the chatbot's reply in the chatbox
          const chatbotResponseLi = createChatLi(chatbotReply, "incoming");
          chatbox.appendChild(chatbotResponseLi);
          chatbox.scrollTo(0, chatbox.scrollHeight);
      })
      .catch(() => {
          // Handle errors
          console.error("Error sending POST request.");
      });
  }, 600);
}
chatInput.addEventListener("input", () => {
    // Adjust the height of the input textarea based on its content
    chatInput.style.height = `${inputInitHeight}px`;
    chatInput.style.height = `${chatInput.scrollHeight}px`;
});

chatInput.addEventListener("keydown", (e) => {
    // If Enter key is pressed without Shift key and the window 
    // width is greater than 800px, handle the chat
    if(e.key === "Enter" && !e.shiftKey && window.innerWidth > 800) {
        e.preventDefault();
        handleChat();
    }
});

sendChatBtn.addEventListener("click", handleChat);
closeBtn.addEventListener("click", () => document.body.classList.remove("show-chatbot"));
chatbotToggler.addEventListener("click", () => document.body.classList.toggle("show-chatbot"));
