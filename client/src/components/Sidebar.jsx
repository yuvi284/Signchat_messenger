import React, { useState } from 'react';
import axios from 'axios';
import { FaBan, FaEllipsisV, FaTrash, FaUserEdit, FaUsers, FaUserPlus } from 'react-icons/fa';
import { MdLogout } from "react-icons/md";
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AddContact from './AddContact';
import ConfirmationModal from './ConfirmationModal';
import InputModal from './InputModal';

const Sidebar = ({ user, contacts, onSelectContact, selectedContact, onContactAdded }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [isAddContactOpen, setIsAddContactOpen] = useState(false);
    const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
    const [openMenuMobile, setOpenMenuMobile] = useState(null);
    const [renameContact, setRenameContact] = useState(null);
    const [renameValue, setRenameValue] = useState('');
    const [deleteContact, setDeleteContact] = useState(null);
    const [blockContact, setBlockContact] = useState(null);
    const { logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        setIsLogoutModalOpen(true);
    };

    const confirmLogout = () => {
        logout();
        setIsLogoutModalOpen(false);
    };

    console.log("Sidebar contacts:", contacts);
    const contactsList = Array.isArray(contacts) ? contacts : [];

    const filteredContacts = contactsList.filter((contact) =>
        (contact.nickname || contact.name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(contact.mobile ?? '').includes(searchTerm)
    );

    // This function clears the selection, making the Sidebar expand again
    const handleShowContacts = () => {
        onSelectContact(null);
    };

    const handleContactAdded = () => {
        // Refresh contacts logic
        if (onContactAdded) onContactAdded();
        else window.location.reload();
    };

    const selectContact = (contact) => {
        onSelectContact({
            mobile: contact.mobile,
            name: contact.nickname || contact.name,
            is_blocked: contact.is_blocked
        });
    };

    const refreshContacts = () => {
        if (onContactAdded) onContactAdded();
    };

    const openRenameModal = (contact) => {
        setOpenMenuMobile(null);
        setRenameContact(contact);
        setRenameValue(contact.nickname || contact.name || '');
    };

    const confirmRename = async () => {
        if (!renameContact || !renameValue.trim()) return;

        try {
            const res = await axios.post('/api/edit_contact_name', {
                mobile: renameContact.mobile,
                new_name: renameValue.trim()
            });

            if (res.data.success) {
                if (selectedContact?.mobile === renameContact.mobile) {
                    onSelectContact({
                        ...selectedContact,
                        name: renameValue.trim()
                    });
                }
                refreshContacts();
                setRenameContact(null);
                setRenameValue('');
            }
        } catch (error) {
            console.error('Error renaming contact', error);
        }
    };

    const confirmDelete = async () => {
        if (!deleteContact) return;

        try {
            await axios.post('/api/delete_contact', { mobile: deleteContact.mobile });
            await axios.post('/api/delete_contact_messages', { mobile: deleteContact.mobile });

            if (selectedContact?.mobile === deleteContact.mobile) {
                onSelectContact(null);
            }
            refreshContacts();
            setDeleteContact(null);
        } catch (error) {
            console.error('Error deleting contact', error);
        }
    };

    const confirmBlockToggle = async () => {
        if (!blockContact) return;

        try {
            const endpoint = blockContact.is_blocked ? '/api/unblock_contact' : '/api/block_contact';
            const res = await axios.post(endpoint, { mobile: blockContact.mobile });

            if (res.data.success) {
                if (selectedContact?.mobile === blockContact.mobile) {
                    onSelectContact({
                        ...selectedContact,
                        is_blocked: !blockContact.is_blocked
                    });
                }
                refreshContacts();
                setBlockContact(null);
            }
        } catch (error) {
            console.error('Error updating block status', error);
        }
    };

    return (
        // Logic: If a contact is selected, add 'mobile-collapsed' class
        <div className={`sidebar ${selectedContact ? 'mobile-collapsed' : ''}`}>
            <div className="sidebar-actions-strip">
                <div className="top-space"></div>

                {/* NEW: Button to slide sidebar content back onto screen */}
                <button
                    className="nav-back-btn"
                    title="Back to Contacts"
                    onClick={handleShowContacts}
                    // Only show this button if a contact is selected and screen is small
                    style={{ display: selectedContact ? 'flex' : 'none' }}
                >
                    <FaUsers />
                </button>

                <button title="Add Contact" onClick={() => setIsAddContactOpen(true)}>
                    <FaUserPlus />
                </button>

                <button title="Edit Profile" onClick={() => navigate('/profile')}>
                    <FaUserEdit />
                </button>
                <button title="Logout" onClick={handleLogout}>
                    <MdLogout />
                </button>
            </div>

            <div className="sidebar-content">
                <div className="brand">Welcome, {user?.username}</div>

                <div className="search-box">
                    <input
                        type="text"
                        placeholder="Search contacts..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>

                <div className="contact-list">
                    {filteredContacts.map((contact) => (
                        <div
                            key={contact.mobile}
                            className={`contact-item ${selectedContact?.mobile === contact.mobile ? 'active' : ''}`}
                            onClick={() => selectContact(contact)}
                            style={{ display: 'flex', alignItems: 'center', padding: '10px', cursor: 'pointer' }}
                        >
                            <img
                                src={contact.profile_picture || '/images/default_user.png'}
                                alt="profile"
                                style={{
                                    width: '40px',
                                    height: '40px',
                                    borderRadius: '50%',
                                    objectFit: 'cover',
                                    marginRight: '10px'
                                }}
                            />
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {contact.nickname || contact.name}
                                </div>
                                {contact.is_blocked && (
                                    <div style={{ color: '#f15c6d', fontSize: '0.75rem', marginTop: '2px' }}>
                                        Blocked
                                    </div>
                                )}
                            </div>
                            {contact.unread > 0 && (
                                <span style={{
                                    backgroundColor: '#25D366',
                                    color: 'white',
                                    borderRadius: '50%',
                                    padding: '2px 6px',
                                    fontSize: '12px',
                                    marginLeft: 'auto',
                                    fontWeight: 'bold',
                                    minWidth: '20px',
                                    textAlign: 'center'
                                }}>
                                    {contact.unread}
                                </span>
                            )}
                            <div style={{ position: 'relative', marginLeft: '8px' }} onClick={(e) => e.stopPropagation()}>
                                <button
                                    className="contact-menu-btn"
                                    title="Contact options"
                                    onClick={() => setOpenMenuMobile(openMenuMobile === contact.mobile ? null : contact.mobile)}
                                >
                                    <FaEllipsisV />
                                </button>

                                {openMenuMobile === contact.mobile && (
                                    <div className="contact-actions-menu">
                                        <button onClick={() => openRenameModal(contact)}>
                                            <FaUserEdit /> Rename
                                        </button>
                                        <button onClick={() => { setOpenMenuMobile(null); setBlockContact(contact); }}>
                                            <FaBan /> {contact.is_blocked ? 'Unblock' : 'Block'}
                                        </button>
                                        <button className="danger" onClick={() => { setOpenMenuMobile(null); setDeleteContact(contact); }}>
                                            <FaTrash /> Delete
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <AddContact
                isOpen={isAddContactOpen}
                onClose={() => setIsAddContactOpen(false)}
                onContactAdded={handleContactAdded}
            />

            <ConfirmationModal
                isOpen={isLogoutModalOpen}
                title="Log out"
                message="Are you sure you want to log out?"
                onConfirm={confirmLogout}
                onCancel={() => setIsLogoutModalOpen(false)}
                confirmText="Log out"
            />

            <InputModal
                isOpen={Boolean(renameContact)}
                title="Rename Contact"
                message="Enter a new name for this contact:"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onConfirm={confirmRename}
                onCancel={() => setRenameContact(null)}
                confirmText="Save"
            />

            <ConfirmationModal
                isOpen={Boolean(deleteContact)}
                title="Delete Contact"
                message={`Delete ${deleteContact?.nickname || deleteContact?.name || 'this contact'} and all messages in this conversation?`}
                onConfirm={confirmDelete}
                onCancel={() => setDeleteContact(null)}
                confirmText="Delete"
            />

            <ConfirmationModal
                isOpen={Boolean(blockContact)}
                title={blockContact?.is_blocked ? 'Unblock Contact' : 'Block Contact'}
                message={
                    blockContact?.is_blocked
                        ? `Unblock ${blockContact?.nickname || blockContact?.name || 'this contact'} so messages can be sent again?`
                        : `Block ${blockContact?.nickname || blockContact?.name || 'this contact'} from sending messages to you?`
                }
                onConfirm={confirmBlockToggle}
                onCancel={() => setBlockContact(null)}
                confirmText={blockContact?.is_blocked ? 'Unblock' : 'Block'}
            />
        </div>
    );
};

export default Sidebar;
