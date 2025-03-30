// script.js

const apiBaseUrl = "https://ilzcew85i3.execute-api.us-east-1.amazonaws.com/dev"; // Your API URL
let updateInterval; // Store the interval ID globally
let resonators = []; // Initialize as empty array
let timerInterval;
let readyCheckInterval;
let clientSideTimerInterval = null; // Variable to hold the interval ID for client-side timers
const READY_CHECK_INTERVAL = 3000; // Check ready status every 3 seconds
const GAME_START_COUNTDOWN = 5; // 5 second countdown before game starts

// Get references to all necessary HTML elements
const createLobbyBtn = document.getElementById("createLobbyBtn");
const joinLobbyBtn = document.getElementById("joinLobbyBtn");
const lobbyCodeInput = document.getElementById("lobbyCodeInput");
const playerNameInput = document.getElementById("playerNameInput");
const deleteLobbyBtn = document.getElementById("deleteLobbyBtn");
const resetLobbyBtn = document.getElementById("resetLobbyBtn"); // Organizer's reset
const leaveLobbyBtn = document.getElementById("leaveLobbyBtn"); // Player's leave
const organizerJoinBtn = document.getElementById("organizerJoinBtn"); // organizer's join as player
const characterContainer = document.getElementById("characterContainer");
const nameError = document.getElementById("nameError");
const codeError = document.getElementById("codeError");
const player1PicksDiv = document.getElementById("player1Picks"); // Added for clearing
const player2PicksDiv = document.getElementById("player2Picks"); // Added for clearing
const bannedResonatorsDiv = document.getElementById("bannedResonators"); // Added for clearing
const joinSection = document.getElementById("joinSection");
const lobbyView = document.getElementById("lobbyView");
const lobbyCodeDisplay = document.getElementById("lobbyCodeDisplay");
const currentGameState = document.getElementById("currentGameState");
const readyButton = document.getElementById('readyButton');


// --- Helper Function to Show/Hide Elements ---
function setElementVisibility(element, visible) {
    if (element) { // Add a check if element exists
       element.classList.toggle("hidden", !visible);
    } else {
        console.warn("Attempted to set visibility for a non-existent element.");
    }
}

function showLobbyView(show) {
    setElementVisibility(lobbyView, show);
    setElementVisibility(joinSection, !show);
}

// --- Helper function to manage button visibility based on role ---
function updateButtonVisibility() {
    const role = localStorage.getItem("role");
    const lobbyCode = localStorage.getItem("lobbyCode");

    // Default: Hide all action buttons if not in a lobby
    let showDelete = false;
    let showReset = false;
    let showJoinAsPlayer = false;
    let showLeave = false;

    if (lobbyCode) {
        // Logic based on the role stored locally
        switch (role) {
            case "organizer":
                showDelete = true;
                showReset = true;
                showJoinAsPlayer = true; // Show Join button for organizer
                showLeave = false;
                break;
            case "organizer_player": // <<< --- New role handler
                showDelete = true;
                showReset = true;
                showJoinAsPlayer = false; // Hide Join button after joining
                showLeave = false;       // Hide Leave button for organizer-player
                break;
            case "player1":
            case "player2":
                showDelete = false;
                showReset = false;
                showJoinAsPlayer = false;
                showLeave = true;        // Show Leave button for regular players
                break;
            default:
                // Unknown role or not logged in correctly, hide all
                console.warn("Unknown role or state:", role);
                break;
        }
    }

    // Apply visibility settings to each button
    // Make sure organizerJoinBtn exists before trying to toggle it
    if(organizerJoinBtn) {
        setElementVisibility(organizerJoinBtn, showJoinAsPlayer);
    } else {
         console.warn("organizerJoinBtn element not found during visibility update.");
    }
    setElementVisibility(deleteLobbyBtn, showDelete);
    setElementVisibility(resetLobbyBtn, showReset);
    setElementVisibility(leaveLobbyBtn, showLeave);
}

// --- Helper function to clear local state and UI ---
function clearLocalLobbyState() {
    localStorage.removeItem("lobbyCode");
    localStorage.removeItem("role");
    localStorage.removeItem("playerName");
    stopPolling();
    if (timerInterval) clearInterval(timerInterval);
    if (readyCheckInterval) clearInterval(readyCheckInterval);
    stopClientSideTimer(); // Clear the client-side timer
    showLobbyView(false);
    updateButtonVisibility();
    lobbyCodeInput.value = "";
    playerNameInput.value = "";
    // Clear pick/ban display areas
    if (player1PicksDiv) {
        const picksContainer = player1PicksDiv.querySelector('.picks-container');
        if (picksContainer) picksContainer.innerHTML = '';
    }
    if (player2PicksDiv) {
        const picksContainer = player2PicksDiv.querySelector('.picks-container');
        if (picksContainer) picksContainer.innerHTML = '';
    }
    if (bannedResonatorsDiv) {
        const bansContainer = bannedResonatorsDiv.querySelector('.bans-container');
        if (bansContainer) bansContainer.innerHTML = '';
    }
    // Reset character button styles with empty arrays
    updateCharacterButtonStyles([], []);
}


// --- Input Error Handling ---
function clearErrors() {
    playerNameInput.classList.remove("error");
    lobbyCodeInput.classList.remove("error");
    nameError.style.display = "none";
    codeError.style.display = "none";
}

function showError(input, errorElement) {
    input.classList.add("error");
    errorElement.style.display = "block";
}

// Add input event listeners to clear error state when user starts typing
playerNameInput.addEventListener("input", () => {
    playerNameInput.classList.remove("error");
    nameError.style.display = "none";
});

lobbyCodeInput.addEventListener("input", () => {
    lobbyCodeInput.classList.remove("error");
    codeError.style.display = "none";
});

// --- Button Event Listeners ---

createLobbyBtn.addEventListener("click", async () => {
    const playerName = playerNameInput.value.trim();
    if (!playerName) {
        alert("Please enter your name first!");
        return;
    }else {
        clearErrors(); // Clear name error if previously shown
    }

    try {
        console.log("Creating lobby with player name:", playerName);
        const requestBody = { playerName: playerName };
        console.log("Request body:", requestBody);
        
        const response = await fetch(`${apiBaseUrl}/lobbies`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody)
        });

        console.log("Response status:", response.status);
        const responseData = await response.json();
        console.log("Response data:", responseData);

        if (response.ok) {
            localStorage.setItem("lobbyCode", responseData.lobbyCode);
            localStorage.setItem("role", "organizer"); // Set role as organizer
            localStorage.setItem("playerName", playerName); // store the name
            showLobbyView(true);
            updateButtonVisibility();
            startPolling();
            updateLobbyData();
        } else {
            alert(`Error creating lobby: ${responseData.error || response.statusText}`);
        }
    } catch (error) {
        console.error("Error creating lobby:", error);
        alert("Network error when creating lobby");
    }
});

joinLobbyBtn.addEventListener("click", async () => {
    const lobbyCode = lobbyCodeInput.value.trim();
    const playerName = playerNameInput.value.trim();

    clearErrors(); // Clear any previous error states

    // Validate inputs with specific error messages
    if (!lobbyCode && !playerName) {
        showError(lobbyCodeInput, codeError);
        showError(playerNameInput, nameError);
        alert("Please enter both lobby code and your name!");
        return;
    }
    
    if (!lobbyCode) {
        showError(lobbyCodeInput, codeError);
        alert("Please enter a lobby code!");
        return;
    }

    if (!playerName) {
        showError(playerNameInput, nameError);
        alert("Please enter your name!");
        return;
    }

    try {
        // First get the current lobby state to check available slots
        const lobbyResponse = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}`, {
            method: "GET",
            headers: { "Content-Type": "application/json" },
        });

        if (!lobbyResponse.ok) {
            const errorData = await lobbyResponse.json();
            if (errorData.error === "Lobby not found") {
                alert("Cannot join: This lobby code does not exist");
            } else {
                alert(`Error checking lobby: ${errorData.error || lobbyResponse.statusText}`);
            }
            return;
        }

        const lobbyData = await lobbyResponse.json();
        
        // Determine which slot to join
        let playerRole;
        
        // If player1 slot is empty, any player (including returning player1) takes it
        if (lobbyData.player1 === '') {
            playerRole = 'player1';
        } else if (lobbyData.player2 === '') {
            playerRole = 'player2';
        } else {
            alert("Cannot join: This lobby is already full");
            return;
        }

        // Now join the lobby with the determined role
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}/join`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                [playerRole]: playerName,
                playerName: playerName // Include both for backwards compatibility
            })
        });

        if (response.ok) {
            const data = await response.json();
            console.log("Join lobby response:", data);
            
            // Store player information with the correct role
            localStorage.setItem("lobbyCode", lobbyCode);
            localStorage.setItem("role", playerRole);
            localStorage.setItem("playerName", playerName);
            
            // Update UI
            showLobbyView(true);
            updateButtonVisibility();
            startPolling();
            updateLobbyData();
        } else {
            const errorData = await response.json();
            console.error("Error joining lobby:", errorData);
            
            // Show specific error message
            if (errorData.error === "Lobby is full") {
                alert("Cannot join: This lobby is already full");
            } else if (errorData.error === "Lobby not found") {
                alert("Cannot join: This lobby code does not exist");
            } else {
                alert(`Error joining lobby: ${errorData.error || response.statusText}`);
            }
            
            // Clear the lobby code input on error
            lobbyCodeInput.value = "";
        }
    } catch (error) {
        console.error("Network error when joining lobby:", error);
        alert("Network error when joining lobby. Please try again.");
    }
});

// --- Organizer's Reset Lobby Button Listener ---
resetLobbyBtn.addEventListener("click", async () => {
    console.log("resetLobbyBtn clicked");
    const lobbyCode = localStorage.getItem("lobbyCode");
    const playerName = localStorage.getItem("playerName"); // <-- Value to check
    const role = localStorage.getItem("role");

    console.log("Reset button check: lobbyCode=", lobbyCode, "role=", role, "playerName=", playerName);

    if (!lobbyCode || !role || !playerName || playerName.trim() === '' || (role !== 'organizer' && role !== 'organizer_player')) {
        alert("Cannot reset: Missing required lobby information, role, or valid player name.");
        console.error("Reset pre-check failed:", { lobbyCode, role, playerName }); // Log failure reason
        return; // Stop if any check fails
    }

    // If the check passes, proceed with confirmation and fetch
    if (!confirm("Reset all picks and bans for this lobby? Players will remain in the lobby.")) return;

    try {
        const payload = { playerName: playerName };
        console.log("Sending reset request with payload:", JSON.stringify(payload)); // Log the payload being sent
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}/reset`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload), // Send the payload
        });
        const data = await response.json();
        if (response.ok) {
            console.log("resetLobby response:", data);
            alert("Lobby reset successfully.");
            updateLobbyData(); // Refresh UI
        } else {
            console.error("Reset lobby failed with status:", response.status, "Data:", data);
            alert(`Error resetting lobby: ${data.error || response.statusText}`);
        }

    } catch (error) {
        console.error("Error resetting lobby:", error);
        alert("Network error resetting lobby.");
    }
});

// --- Player's Leave Lobby Button Listener ---
leaveLobbyBtn.addEventListener("click", async () => {
    console.log("leaveLobbyBtn clicked");
    const lobbyCode = localStorage.getItem("lobbyCode");
    const playerRole = localStorage.getItem("role"); // 'player1' or 'player2'
    const playerName = localStorage.getItem("playerName");

    if (!lobbyCode || (playerRole !== 'player1' && playerRole !== 'player2')) {
        // If somehow this button is visible when it shouldn't be, just clear local state
        clearLocalLobbyState();
        alert("State cleared.");
        return;
    }

    if (!confirm("Leave the lobby? This will clear all current picks and bans.")) return;

    try {
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}/leave`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ player: playerRole }),
        });

        // Clear local state before handling response
        clearLocalLobbyState();

        if (response.ok) {
            console.log("leaveLobby response: OK");
            alert("You have left the lobby successfully.");
        } else {
            // Handle different error status codes
            switch (response.status) {
                case 502:
                    console.error("Server error (502) when leaving lobby");
                    alert("You have left the lobby. Note: The server experienced an error, but your local state has been cleared.");
                    break;
                case 404:
                    console.error("Lobby not found (404) when leaving");
                    alert("You have left the lobby. Note: The lobby was not found on the server.");
                    break;
                default:
                    try {
                        const errorData = await response.json();
                        console.error("Error leaving lobby:", errorData);
                        alert(`You have left the lobby. Server message: ${errorData.error || response.statusText}`);
                    } catch (parseError) {
                        console.error("Failed to parse error response:", response.statusText);
                        alert(`You have left the lobby. Server status: ${response.status} ${response.statusText}`);
                    }
            }
        }
    } catch (error) {
        console.error("Network error when leaving lobby:", error);
        // Ensure local state is cleared even if server request fails
        clearLocalLobbyState();
        alert("You have left the lobby. Note: Could not communicate with server, but local state has been cleared.");
    }
});

// --- Organizer's Delete Lobby Button Listener ---
deleteLobbyBtn.addEventListener("click", async () => {
    console.log("deleteLobbyBtn clicked");
    const lobbyCode = localStorage.getItem("lobbyCode");
    const playerName = localStorage.getItem("playerName");
    const role = localStorage.getItem("role");
    
    if (!lobbyCode || (role !== 'organizer' && role !== 'organizer_player')) {
        alert("No lobby code found or not organizer.");
        return;
    }
    if (!confirm("Delete lobby permanently?")) return;

    try {
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ playerName: playerName })
        });
        if (response.ok) {
            console.log("deleteLobby response: OK");
            clearLocalLobbyState(); // Clear local state after successful delete
            alert("Lobby deleted.");
        } else {
            try {
                const data = await response.json();
                alert(`Error deleting lobby: ${data.error || response.statusText}`);
            } catch (parseError) {
                alert(`Error deleting lobby: ${response.statusText}`);
            }
        }
    } catch (error) {
        console.error("Error deleting lobby:", error);
        alert("Network error deleting lobby.");
    }
});

// --- Organizer's Join as Player Button Listener ---
organizerJoinBtn.addEventListener("click", async () => {
    console.log("organizerJoinBtn clicked");
    const lobbyCode = localStorage.getItem("lobbyCode");
    // Retrieve the organizer's name stored during creation
    const organizerPlayerName = localStorage.getItem("playerName");
    const currentRole = localStorage.getItem("role");

    // Basic validation
    if (currentRole !== 'organizer') {
        console.error("Attempted organizer join but role is not 'organizer'. Role:", currentRole);
        alert("Error: Action only available for the organizer.");
        return;
    }
    if (!lobbyCode) {
        console.error("Attempted organizer join but lobbyCode is missing from localStorage.");
        alert("Error: Lobby code not found. Please refresh.");
        clearLocalLobbyState(); // Clear potentially inconsistent state
        return;
    }
    if (!organizerPlayerName) {
        console.error("Attempted organizer join but playerName is missing from localStorage.");
        alert("Error: Organizer name not found. Please refresh or recreate lobby.");
        // Consider clearing state or prompting, but alert for now
        return;
    }

    console.log(`Attempting to join lobby ${lobbyCode} as player ${organizerPlayerName}`);

    try {
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}/organizer-join`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // Send organizer name in the body (INSECURE METHOD)
            body: JSON.stringify({ playerName: organizerPlayerName }),
        });

        if (response.ok) {
            const data = await response.json();
            console.log("Organizer join response:", data);
            // Check if backend confirms the role change
            if (data.newRole === 'organizer_player') {
                // Update local role state
                localStorage.setItem("role", "organizer_player");
                console.log("Role updated locally to organizer_player");

                // Refresh UI immediately
                updateButtonVisibility();
                updateLobbyData(); // Fetch latest lobby state to show the user in player slot

                // Optional: Provide feedback
                // outputDiv.innerHTML = "<p>Successfully joined as player.</p>"; // Might be overwritten by updateLobbyData
                alert("Successfully joined as a player!");

            } else {
                console.error("Backend response OK but did not confirm organizer_player role:", data);
                alert("Error: Could not confirm role change with backend.");
            }
        } else {
            // Handle specific errors first
            if (response.status === 409) { // 409 Conflict - Lobby is full
                 const errorData = await response.json().catch(() => ({ error: "Lobby is full" }));
                 console.warn("Organizer join failed: Lobby is full.");
                 alert(`Cannot join: ${errorData.error || "Lobby is full"}`);

            } else if (response.status === 403) { // 403 Forbidden - Not organizer (based on backend check)
                 const errorData = await response.json().catch(() => ({ error: "Authorization failed" }));
                 console.error("Organizer join failed: Authorization error from backend.", errorData);
                 alert(`Error: ${errorData.error || "Authorization failed."}`);
                 // It might be wise to clear local state if auth fails severely
                 // clearLocalLobbyState();

            } else { // Handle other non-OK responses (400, 404, 500, etc.)
                const errorData = await response.json().catch(() => ({ error: response.statusText }));
                console.error(`Organizer join failed: ${response.status}`, errorData);
                alert(`Error joining as player: ${errorData.error || response.statusText}`);
            }
        }
    } catch (error) {
        console.error("Network error during organizer join:", error);
        alert("Network error trying to join as player. Please check connection and try again.");
    }
});

// --- Pick Functionality ---
async function makePick(pickId) {
    console.log("makePick called with:", pickId);
    const lobbyCode = localStorage.getItem("lobbyCode");
    let player = localStorage.getItem("role"); // 'player1', 'player2', or 'organizer_player'

    if (!lobbyCode || !player || (player !== 'player1' && player !== 'player2' && player !== 'organizer_player')) {
        alert("Not in a valid lobby or role cannot make picks/bans.");
        console.error("makePick pre-check failed:", { lobbyCode, player });
        return;
    }

    // If player is organizer_player, backend (makePick.py) needs to resolve it.
    // Ensure makePick.py can handle receiving 'organizer_player' as the player value
    // OR resolve it here (more complex, requires fetching state first).
    // Sending 'organizer_player' is simpler for now if backend handles it.

    const payload = {
        player: player, // Send the role ('player1', 'player2', or 'organizer_player')
        pick: pickId    // Send the resonator ID under the 'pick' key
    }
    console.log("Sending pick/ban request with payload:", JSON.stringify(payload));

    try {
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}/action`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json(); // Attempt to parse JSON regardless of status
        if (response.ok) {
            console.log("makePick response:", data);
            updateLobbyData(); // Refresh data after pick/ban
        } else {
            console.error("Error making pick/ban:", response.status, data);
             alert(`Error making pick/ban: ${data.error || response.statusText}`);
        }
    } catch (error) {
        console.error("Error making pick/ban:", error);
        alert("Network error making pick/ban.");
    }
}

// --- Data Fetching and Display ---

async function updateLobbyData() {
    const lobbyCode = localStorage.getItem("lobbyCode");
    const currentRole = localStorage.getItem("role");
    const currentName = localStorage.getItem("playerName");

    if (!lobbyCode) {
        clearLocalLobbyState();
        return;
    }

    try {
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}`, {
            method: "GET",
            headers: { "Content-Type": "application/json" },
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: response.statusText }));
            console.error("Error fetching lobby data:", errorData);
            if (response.status === 404) {
                console.log("Lobby not found on server, clearing local state.");
                // *** ADD THE POP-UP ALERT HERE ***
                 alert("The lobby was closed by the organizer."); 

                clearLocalLobbyState(); // Then clear state
                } else {
                // Handle other non-404 errors if needed
                clearLocalLobbyState();
            }
            return;
        }

        const data = await response.json();
        console.log("  Lobby Data:", data);

        // Update lobby info display
        if (lobbyCodeDisplay) lobbyCodeDisplay.textContent = lobbyCode;
        
        // Update game state display
        if (currentGameState) {
            currentGameState.textContent = data.gameState || 'waiting';
        }

        // Update player names
        const player1NameDiv = document.getElementById('player1Name');
        const player2NameDiv = document.getElementById('player2Name');
        if (player1NameDiv) player1NameDiv.textContent = data.player1 || 'None';
        if (player2NameDiv) player2NameDiv.textContent = data.player2 || 'None';

        // Handle ready check UI
        const readyCheckContainer = document.getElementById('readyCheckContainer');
        const player1Status = document.getElementById('player1Status');
        const player2Status = document.getElementById('player2Status');
        const readyButton = document.getElementById('readyButton');

        // Show ready check UI if both players are present and game state is ready_check
        if (data.player1 && data.player2 && data.gameState === 'ready_check') {
            // Show ready check UI
            if (readyCheckContainer) readyCheckContainer.classList.remove('hidden');

            // Update player status displays
            if (player1Status) player1Status.textContent = `Player 1: ${data.player1Ready ? 'Ready' : 'Not Ready'}`;
            if (player2Status) player2Status.textContent = `Player 2: ${data.player2Ready ? 'Ready' : 'Not Ready'}`;

            // Update ready button state based on player role
            if (readyButton) {
                // Check if current user is organizer_player and match to player1 or player2
                if (currentRole === 'organizer_player') {
                    const organizerName = currentName;
                    if (organizerName === data.player1) {
                        // Organizer is player1
                        readyButton.disabled = data.player1Ready;
                        readyButton.textContent = data.player1Ready ? 'Waiting...' : 'Ready';
                        readyButton.style.display = '';
                    } else if (organizerName === data.player2) {
                        // Organizer is player2
                        readyButton.disabled = data.player2Ready;
                        readyButton.textContent = data.player2Ready ? 'Waiting...' : 'Ready';
                        readyButton.style.display = '';
                    } else {
                        // Hide ready button if organizer is not a player
                                    // Organizer name doesn't match P1 or P2 - Hide button
                        console.error("Organizer_player role mismatch: Name from localStorage doesn't match player slots from backend.", { organizerName, player1: data.player1, player2: data.player2 });
                        readyButton.disabled = true;
                        readyButton.style.display = 'none';
                    }
                } else if (currentRole === 'player1') {
                    readyButton.disabled = data.player1Ready;
                    readyButton.textContent = data.player1Ready ? 'Waiting...' : 'Ready';
                    readyButton.style.display = '';
                } else if (currentRole === 'player2') {
                    readyButton.disabled = data.player2Ready;
                    readyButton.textContent = data.player2Ready ? 'Waiting...' : 'Ready';
                    readyButton.style.display = '';
                } else {
                    // Organizer (not player) or unknown role - Hide button
                    readyButton.disabled = true;
                    readyButton.style.display = 'none';
                }
            }
        } else {
            // Hide ready check UI
            if (readyCheckContainer) readyCheckContainer.classList.add('hidden');
        }

        // Update game phase UI
        updateGamePhaseUI(data);

        // Update picks and bans
        if (data.picks) {
            displayPicks('player1', data.player1, data.picks);
            displayPicks('player2', data.player2, data.picks);
        }
        if (data.bans) {
            displayBans(data.bans);
        }

        // Update character button styles
        updateCharacterButtonStyles(data.picks || [], data.bans || []);

    } catch (error) {
        console.error("Error in updateLobbyData:", error);
    }
}

async function copyLobbyCode(code) {
    const copyBtn = document.getElementById('copyCodeBtn');
    if (!copyBtn) return;

    // Try the modern clipboard API first
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(code);
            copyBtn.textContent = "Copied!";
            copyBtn.classList.add("copied");
            setTimeout(() => {
                copyBtn.textContent = "Copy Code";
                copyBtn.classList.remove("copied");
            }, 2000);
            return;
        } catch (err) {
            console.log("Clipboard API failed, falling back to execCommand", err);
        }
    }

    // Fallback to execCommand
    try {
        const tempInput = document.createElement('textarea');
        tempInput.value = code;
        tempInput.style.position = 'fixed';
        tempInput.style.left = '-9999px';
        tempInput.style.top = '0';
        document.body.appendChild(tempInput);
        tempInput.focus();
        tempInput.select();
        
        const successful = document.execCommand('copy');
        document.body.removeChild(tempInput);

        if (successful) {
            copyBtn.textContent = "Copied!";
            copyBtn.classList.add("copied");
            setTimeout(() => {
                copyBtn.textContent = "Copy Code";
                copyBtn.classList.remove("copied");
            }, 2000);
        } else {
            throw new Error('Copy command failed');
        }
    } catch (err) {
        console.error("Fallback copy failed:", err);
        // Final fallback: show the code in a prompt
        copyBtn.textContent = "Copy failed";
        setTimeout(() => {
            copyBtn.textContent = "Copy Code";
        }, 2000);
        alert("Please copy this code manually: " + code);
    }
}

// --- Function to display picks for a player ---
function displayPicks(playerIdentifier, playerName, allPicks) {
    const containerId = `${playerIdentifier}Picks`;
    const container = document.getElementById(containerId);
    if (!container) return;

    const picksContainer = container.querySelector('.picks-container');
    if (!picksContainer) return;

    // Clear existing picks
    picksContainer.innerHTML = '';

    // Filter picks for this player
    const playerPicks = (allPicks || []).filter((pickId, index) => {
        if (playerIdentifier === 'player1') {
            return index % 2 === 0;
        } else {
            return index % 2 !== 0;
        }
    });

    // Update player name
    const nameElement = container.querySelector('.player-name');
    if (nameElement) {
        nameElement.textContent = playerName || playerIdentifier;
    }

    // Add pick images
    playerPicks.forEach(pickId => {
        const resonator = resonators.find(r => r.id === pickId);
        if (resonator) {
            const img = document.createElement('img');
            img.src = resonator.image;
            img.alt = resonator.name;
            img.title = resonator.name;
            picksContainer.appendChild(img);
        }
    });
}

// --- Function to display banned resonators ---
function displayBans(bans) {
    const container = document.getElementById('globalBansSection');
    if (!container) return;

    const bansContainer = container.querySelector('.bans-container');
    if (!bansContainer) return;

    // Clear existing bans
    bansContainer.innerHTML = '';

    if (bans && bans.length > 0) {
        bans.forEach(banId => {
            const resonator = resonators.find(r => r.id === banId);
            if (resonator) {
                const img = document.createElement('img');
                img.src = resonator.image;
                img.alt = resonator.name;
                img.title = resonator.name;
                bansContainer.appendChild(img);
            }
        });
    }
}

// --- Function to update character button styles ---
function updateCharacterButtonStyles(picks, bans) {
    const buttons = document.querySelectorAll('.character-button');
    buttons.forEach(button => {
        const resonatorId = button.dataset.resonatorId;
        button.classList.remove('picked-p1', 'picked-p2', 'banned');
        button.disabled = false;

        if (bans && bans.includes(resonatorId)) {
            button.classList.add('banned');
            button.disabled = true;
        } else if (picks) {
            // Determine which player picked this resonator
            const pickIndex = picks.indexOf(resonatorId);
            if (pickIndex !== -1) {
                const playerClass = pickIndex % 2 === 0 ? 'picked-p1' : 'picked-p2';
                button.classList.add(playerClass);
                button.disabled = true;
            }
        }
    });
}

// --- Function to create character buttons ---
function createCharacterButtons() {
    if (!characterContainer) return;
    characterContainer.innerHTML = ''; // Clear existing buttons
    resonators.forEach(resonator => {
        const button = document.createElement('button');
        button.classList.add('character-button');
        button.style.backgroundImage = `url(${resonator.image})`;
        button.dataset.resonatorId = resonator.id;
        button.title = resonator.name;
        button.addEventListener('click', () => makePick(resonator.id));
        characterContainer.appendChild(button);
    });
}

// --- Polling Functions ---
function startPolling() {
    console.log("startPolling called");
    if (updateInterval) {
        console.log("  Clearing existing interval");
        clearInterval(updateInterval);
    }
    updateLobbyData(); // Update immediately when starting polling
    updateInterval = setInterval(() => {
        //console.log("  Polling interval tick"); // Can be noisy, uncomment for debugging
        updateLobbyData();
    }, 3000); // Increased interval slightly to 3 seconds
    console.log("  Polling interval set");
}

function stopPolling() {
    console.log("stopPolling called");
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
}

// --- Initial Page Load Setup ---
async function initializePage() {
    console.log("initializePage called");

    let isWindowClosing = false;

    // Add beforeunload event listener for cleanup
    window.addEventListener('beforeunload', async (event) => {
        const lobbyCode = localStorage.getItem("lobbyCode");
        const role = localStorage.getItem("role");
        const playerName = localStorage.getItem("playerName");

        if (lobbyCode && role && playerName) {
            try {
                // For regular players, leave the lobby
                if (role === 'player1' || role === 'player2') {
                    await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}/leave`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ player: role }),
                        keepalive: true
                    });
                }
                // For organizer or organizer-player, delete the lobby
                else if (role === 'organizer' || role === 'organizer_player') {
                    await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}`, {
                        method: "DELETE",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ playerName: playerName }),
                        keepalive: true
                    });
                }
                isWindowClosing = true;
            } catch (error) {
                console.error("Error during cleanup:", error);
            }
        }
    });

    // Add unload event listener for localStorage cleanup
    window.addEventListener('unload', (event) => {
        if (isWindowClosing) {
            localStorage.removeItem("lobbyCode");
            localStorage.removeItem("role");
            localStorage.removeItem("playerName");
        }
    });

    // Load Resonator data first
    try {
        const response = await fetch('resonators.json');
        if (!response.ok) {
            throw new Error(`Failed to load resonators.json: ${response.status}`);
        }
        resonators = await response.json();
        createCharacterButtons(); // Create buttons once data is loaded
    } catch (error) {
        console.error("Error loading resonators:", error);
        return; // Stop initialization
    }

    // Now check lobby state
    const lobbyCode = localStorage.getItem("lobbyCode");
    const role = localStorage.getItem("role");
    const playerName = localStorage.getItem("playerName");
    console.log("  Initial Lobby Code:", lobbyCode);

    if (lobbyCode && role && playerName) {
        try {
            // Check if the player's slot still exists in the lobby
            const lobbyResponse = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}`, {
                method: "GET",
                headers: { "Content-Type": "application/json" },
            });

            if (!lobbyResponse.ok) {
                // If lobby doesn't exist or other error, clear local state
                clearLocalLobbyState();
                return;
            }

            const lobbyData = await lobbyResponse.json();
            
            // Check if the player's slot matches their role
            if (role === 'player1' && lobbyData.player1 !== playerName) {
                clearLocalLobbyState();
                return;
            }
            if (role === 'player2' && lobbyData.player2 !== playerName) {
                clearLocalLobbyState();
                return;
            }
            if ((role === 'organizer' || role === 'organizer_player') && lobbyData.organizerName !== playerName) {
                clearLocalLobbyState();
                return;
            }

            // If we get here, the player's slot is still valid
            showLobbyView(true);
            startPolling();
            updateLobbyData();
        } catch (error) {
            console.error("Error checking lobby state:", error);
            clearLocalLobbyState();
        }
    } else {
        showLobbyView(false);
    }
    updateButtonVisibility(); // Set initial button visibility
}

// --- Timer Management Functions ---
function startClientSideTimer(startTime, duration) {
    const timerElement = document.getElementById('timer');
    if (!timerElement) return;

    // Clear any existing timer
    stopClientSideTimer();

    // Calculate end time
    const endTime = startTime + duration;

    // Update display immediately
    updateTimerDisplay(endTime);

    // Start interval for smooth updates
    clientSideTimerInterval = setInterval(() => {
        updateTimerDisplay(endTime);
    }, 1000);
}

function updateTimerDisplay(endTime) {
    const timerElement = document.getElementById('timer');
    if (!timerElement) return;

    const now = Date.now();
    const remaining = Math.max(0, endTime - now);
    const seconds = Math.ceil(remaining / 1000);

    if (remaining <= 0) {
        timerElement.textContent = "Time expired!";
        timerElement.classList.add('warning');
        stopClientSideTimer();
        // The backend will handle the auto-selection
        updateLobbyData();
    } else {
        timerElement.textContent = `Time remaining: ${seconds}s`;
        if (seconds <= 10) {
            timerElement.classList.add('warning');
        } else {
            timerElement.classList.remove('warning');
        }
    }
}

function stopClientSideTimer() {
    if (clientSideTimerInterval) {
        clearInterval(clientSideTimerInterval);
        clientSideTimerInterval = null;
    }
}

// --- Optional: Helper function for cleaner mapping ---
function getFriendlyPhaseName(gameState) {
    if (!gameState) return 'Unknown';
    if (gameState.startsWith('ban1')) return 'Ban Phase 1';
    if (gameState.startsWith('pick1')) return 'Pick Phase 1';
    if (gameState.startsWith('ban2')) return 'Ban Phase 2';
    if (gameState.startsWith('pick2')) return 'Pick Phase 2';
    // Handle specific states or fallbacks
    switch (gameState) {
        case 'waiting': return 'Waiting';
        case 'ready_check': return 'Ready Check';
        case 'complete': return 'Complete';
        default: return gameState; // Fallback to internal name if unknown
    }
}

function updateGamePhaseUI(data) {
    // Get references (ensure these are correct)
    const gameStatusHeader = document.getElementById('gameStatusHeader');
    const currentPhase = document.getElementById('currentPhase');
    const turnIndicator = document.getElementById('turnIndicator'); // Primary message display
    const pickBanSection = document.querySelector('.pick-ban-section');
    const pickBanTitle = document.getElementById('pickBanTitle'); // Reference to element being removed
    const timer = document.getElementById('timer');
    const characterContainer = document.getElementById('characterContainer');
    const globalBansSection = document.getElementById('globalBansSection');
    const readyCheckContainer = document.getElementById('readyCheckContainer');

    // Get friendly phase name
    const friendlyPhaseName = getFriendlyPhaseName(data.gameState);

     // Basic check if elements exist
     if (!gameStatusHeader || !currentPhase || !turnIndicator || !pickBanSection /* removed pickBanTitle check */ || !timer || !characterContainer || !globalBansSection || !readyCheckContainer) {
          console.error("One or more critical UI elements missing in updateGamePhaseUI");
          return; // Exit if elements aren't found
     }

    // --- Ensure Top Header is Always Visible (Except during Ready Check) ---
    // --- and Pick/Ban Section is visible when active ---
    let showHeader = true;
    let showPickBanArea = false; // Hide by default, show during active phases
    let showReadyCheck = false;

    // Determine visibility based on state
    if (data.gameState === 'ready_check') {
        showHeader = false;
        showReadyCheck = true;
    } else if (data.gameState !== 'waiting') {
        // Show pick/ban area for all states other than waiting and ready_check
        showPickBanArea = true;
    } // Header remains visible for 'waiting' and active states

    setElementVisibility(gameStatusHeader, showHeader);
    setElementVisibility(pickBanSection, showPickBanArea);
    setElementVisibility(readyCheckContainer, showReadyCheck);

    // --- Update Content Based on State ---
    let statusMessage = ''; // This will go into turnIndicator
    let activePlayer = null;

    // Always update the raw phase text if header is visible
    if (showHeader) {
        currentPhase.textContent = `Current Phase: ${friendlyPhaseName}`;
    }

    // --- Use NEW State Names in Switch ---
    switch (data.gameState) {
        case 'waiting':
            statusMessage = "Waiting for players to join...";
            break;
        case 'ready_check':
            // Handled by ready check container visibility
            break;
        // Ban Phase 1
        case 'ban1_p1':
            statusMessage = "Player 1: Ban 1 Resonator";
            activePlayer = 'player1';
            break;
        case 'ban1_p2':
            statusMessage = "Player 2: Ban 1 Resonator";
            activePlayer = 'player2';
            break;
        // Pick Phase 1
        case 'pick1_p1':
            statusMessage = "Player 1: Pick 1st Resonator (of 2)";
            activePlayer = 'player1';
            break;
        case 'pick1_p2':
            statusMessage = "Player 2: Pick 1st Resonator (of 2)";
            activePlayer = 'player2';
            break;
        case 'pick1_p1_2':
            statusMessage = "Player 1: Pick 2nd Resonator (of 2)";
            activePlayer = 'player1';
            break;
        case 'pick1_p2_2':
            statusMessage = "Player 2: Pick 2nd Resonator (of 2)";
            activePlayer = 'player2';
            break;
        // Ban Phase 2
        case 'ban2_p1':
            statusMessage = "Player 1: Ban 1 Resonator";
            activePlayer = 'player1';
            break;
        case 'ban2_p2':
            statusMessage = "Player 2: Ban 1 Resonator";
            activePlayer = 'player2';
            break;
        // Pick Phase 2
        case 'pick2_p2': // Note: Player 2 starts this pick phase
            statusMessage = "Player 2: Pick Final Resonator";
            activePlayer = 'player2';
            break;
        case 'pick2_p1':
            statusMessage = "Player 1: Pick Final Resonator";
            activePlayer = 'player1';
            break;
        // Complete
        case 'complete':
            statusMessage = "Pick/Ban Phase Complete!";
            // setElementVisibility(characterContainer, false); // Keep grid visible?
            break;
        default:
            statusMessage = `Unknown State: ${data.gameState}`;
    }
    // --- End Switch Updates ---

    // --- Update the #turnIndicator in the header ---
    if (showHeader) {
        turnIndicator.textContent = statusMessage;
    }

    // --- Ensure the (now unused) #pickBanTitle element is cleared/hidden if it still exists ---
    // This line is just defensive coding in case HTML isn't updated immediately.
    if (pickBanTitle) pickBanTitle.textContent = '';

    // --- Handle Timer Visibility ---
    if (showPickBanArea && data.timerState && data.timerState.isActive && data.timerState.startTime && data.timerState.duration) {
        startClientSideTimer(data.timerState.startTime, data.timerState.duration);
        setElementVisibility(timer, true);
    } else {
        stopClientSideTimer();
        setElementVisibility(timer, false); // Hiding timer when inactive
        if(timer) timer.textContent = "Time remaining: --";
        if(timer) timer.classList.remove('warning');
    }

     // --- Ensure Character Grid Visibility ---
     // Show grid if pick/ban area is shown
     setElementVisibility(characterContainer, showPickBanArea);

    // --- Ensure Global Bans Section Visibility ---
     // Show bans if pick/ban area is shown (or always show if header is visible too?)
     // Let's show bans whenever the header OR the pick/ban area is shown (except ready_check)
    setElementVisibility(globalBansSection, showHeader || showPickBanArea);

    // --- Handle Active Player Highlight ---
    updateActivePlayerHighlight(activePlayer);
}

function updateActivePlayerHighlight(activePlayer) {
    const player1Section = document.getElementById('player1Section');
    const player2Section = document.getElementById('player2Section');

    if (player1Section && player2Section) {
        player1Section.classList.remove('active-turn');
        player2Section.classList.remove('active-turn');

        if (activePlayer === 'player1') {
            player1Section.classList.add('active-turn');
        } else if (activePlayer === 'player2') {
            player2Section.classList.add('active-turn');
        }
    }
}

function startGameCountdown() {
    let countdown = GAME_START_COUNTDOWN;
    const countdownDisplay = document.getElementById('readyPhaseTimer');
    
    const countdownInterval = setInterval(() => {
        countdownDisplay.textContent = `Starting in: ${countdown}...`;
        countdown--;
        
        if (countdown < 0) {
            clearInterval(countdownInterval);
            startPickBanPhase();
        }
    }, 1000);
}

function startPickBanPhase() {
    const readyCheckContainer = document.getElementById('readyCheckContainer');
    const gamePhaseContainer = document.getElementById('gamePhaseContainer');
    
    readyCheckContainer.classList.add('hidden');
    gamePhaseContainer.classList.remove('hidden');
    
    // Start polling for game state
    startPolling();
}

function updateReadyUI(data) {
    const readyCheckContainer = document.getElementById('readyCheckContainer');
    const gamePhaseContainer = document.getElementById('gamePhaseContainer');
    const player1Status = document.getElementById('player1Status');
    const player2Status = document.getElementById('player2Status');
    const readyButton = document.getElementById('readyButton');
    const playerRole = localStorage.getItem('role');
    
    // Update ready status displays
    player1Status.textContent = `Player 1: ${data.player1Ready ? 'Ready' : 'Not Ready'}`;
    player2Status.textContent = `Player 2: ${data.player2Ready ? 'Ready' : 'Not Ready'}`;
    
    // Show/hide ready check container based on game state
    if (data.gameState === 'ready_check') {
        readyCheckContainer.classList.remove('hidden');
        gamePhaseContainer.classList.add('hidden');
        
        // Update ready button state
        if (playerRole === 'player1') {
            readyButton.disabled = data.player1Ready;
            readyButton.textContent = data.player1Ready ? 'Waiting...' : 'Ready';
        } else if (playerRole === 'player2') {
            readyButton.disabled = data.player2Ready;
            readyButton.textContent = data.player2Ready ? 'Waiting...' : 'Ready';
        }
    } else {
        readyCheckContainer.classList.add('hidden');
        gamePhaseContainer.classList.remove('hidden');
    }
}

// --- Ready Button Event Listener ---
readyButton.addEventListener("click", async () => {
    console.log("readyButton clicked");
    const lobbyCode = localStorage.getItem("lobbyCode");
    const playerRole = localStorage.getItem("role");
    const currentName = localStorage.getItem("playerName");

    if (!lobbyCode || !playerRole || !currentName) {
        alert("Missing required data to mark ready.");
        return;
    }

    // Determine actual player role
    let actualRole = playerRole;
    if (playerRole === 'organizer_player') {
        // Organizer-player can be either player1 or player2 depending on lobby state
        // We'll let the backend determine this
        actualRole = 'organizer_player';
    } else if (playerRole !== 'player1' && playerRole !== 'player2') {
        alert("Only players can mark themselves as ready.");
        return;
    }

    try {
        console.log(`Marking ${actualRole} as ready in lobby ${lobbyCode}`);
        
        // Update ready status through the main lobby endpoint
        const response = await fetch(`${apiBaseUrl}/lobbies/${lobbyCode}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'ready',
                player: actualRole,
                ready: true
            })
        });

        console.log("Ready response status:", response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error("Error response:", errorText);
            let errorData;
            try {
                errorData = JSON.parse(errorText);
            } catch (e) {
                errorData = { error: response.statusText };
            }
            throw new Error(errorData.error || response.statusText);
        }

        const data = await response.json();
        console.log("Ready response data:", data);
        
        // Update UI based on response
        readyButton.textContent = 'Waiting...';
        readyButton.disabled = true;

        // Update player status displays
        const player1Status = document.getElementById('player1Status');
        const player2Status = document.getElementById('player2Status');
        if (player1Status) player1Status.textContent = `Player 1: ${data.lobbyState.player1Ready ? 'Ready' : 'Not Ready'}`;
        if (player2Status) player2Status.textContent = `Player 2: ${data.lobbyState.player2Ready ? 'Ready' : 'Not Ready'}`;

        // Check if both players are ready
        if (data.lobbyState.player1Ready && data.lobbyState.player2Ready) {
            // Start countdown to game start
            startGameCountdown();
        }

        // Start polling for updates
        startPolling();

    } catch (error) {
        console.error('Error marking ready:', error);
        alert('Failed to mark ready. Please try again.');
        // Reset button state on error
        readyButton.textContent = 'Ready';
        readyButton.disabled = false;
    }
});

initializePage(); // Run initialization when the script loads