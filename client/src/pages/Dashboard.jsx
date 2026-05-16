import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Sidebar from '../components/Sidebar';
import ChatArea from '../components/ChatArea';
import { useAuth } from '../context/AuthContext';
import './Dashboard.css';

const Dashboard = () => {
    const { user } = useAuth();
    const [contacts, setContacts] = useState({});
    const [selectedContact, setSelectedContact] = useState(null);

    useEffect(() => {
        fetchContacts();

        // Poll for contact updates (badges) every 3 seconds
        const intervalId = setInterval(() => {
            fetchContacts();
        }, 3000);

        return () => clearInterval(intervalId);
    }, []);

    const fetchContacts = async () => {
        try {
            const res = await axios.get('/api/get_saved_contacts');
            // console.log("Fetched contacts:", res.data.contacts); 
            setContacts(res.data.contacts || {});
        } catch (error) {
            console.error("Error fetching contacts", error);
        }
    };

    const handleSelectContact = (contact) => {
        setSelectedContact(contact);
        // We no longer manually hide the sidebar here. 
        // The CSS will handle the layout based on selectedContact existing.
    };

    const handleBackToSidebar = () => {
        setSelectedContact(null);
    };

    return (
        <div className="dashboard-container">
            {/* 1. We pass selectedContact to Sidebar so it knows when to shrink */}
            <Sidebar
                user={user}
                contacts={contacts}
                onSelectContact={handleSelectContact}
                selectedContact={selectedContact}
                onContactAdded={fetchContacts}
            />

            {/* 2. Chat Area shows up when a contact is selected */}
            <div className={`main-content ${selectedContact ? 'show' : ''}`}>
                {selectedContact ? (
                    <ChatArea
                        contact={selectedContact}
                        currentUser={user}
                        onBack={handleBackToSidebar}
                        onMessageUpdate={fetchContacts}
                    />
                ) : (
                    /* This welcome screen is hidden on mobile via CSS when no chat is selected */
                    <div className="welcome-message">
                        <h2>SignChat Messenger</h2>
                        <p>Connect with your students and colleagues through text and Indian Sign Language.</p>
                        <div className="features">
                            <div className="feature-card">
                                <i className="fas fa-hands"></i>
                                <h3>Sign Language</h3>
                                <p>Convert messages to ISL videos</p>
                            </div>
                            <div className="feature-card">
                                <i className="fas fa-camera"></i>
                                <h3>Sign Detection</h3>
                                <p>Real-time sign to text conversion</p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Dashboard;