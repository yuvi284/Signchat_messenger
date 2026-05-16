import React, { useState } from 'react';
import axios from 'axios';

const AddContact = ({ isOpen, onClose, onContactAdded }) => {
    const [mobile, setMobile] = useState('');
    const [searchResult, setSearchResult] = useState(null);
    const [nickname, setNickname] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const normalizeMobile = (value) => String(value ?? '').trim();

    if (!isOpen) return null;

    const handleSearch = async () => {
        if (!mobile) {
            setError('Please enter a mobile number');
            return;
        }
        setLoading(true);
        setError('');
        setSearchResult(null);

        try {
            const res = await axios.get(`/api/search_contact?mobile=${mobile}`);
            if (res.data.status === 'not_registered') {
                setError('User not registered on SignChat.');
            } else if (res.data.status === 'error') {
                setError('Error searching for user.');
            } else if (res.data.status === 'multiple' || res.data.contacts) {
                // The backend returns a list, but we searched by a specific mobile, 
                // so we expect the first one to be the match or we filter.
                // Based on backend logic: it returns a list.
                const contacts = res.data.contacts;
                const searchedMobile = normalizeMobile(mobile);
                const match = contacts.find(c => normalizeMobile(c.mobile) === searchedMobile);

                if (match) {
                    if (match.status === 'saved') {
                        setError('User is already in your contacts.');
                    } else {
                        setSearchResult(match);
                        setNickname(match.name); // Default nickname to username
                    }
                } else {
                    // Fallback if exact match not found in the list (fuzzy search might return others)
                    if (contacts.length > 0) {
                        // Just show the first one or ask user? 
                        // For exact mobile search, let's assume the first one is relevant if mobile matches
                        // But let's be strict about mobile match
                        setError('User not found.');
                    } else {
                        setError('User not found.');
                    }
                }
            }
        } catch (err) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleAdd = async () => {
        if (!searchResult) return;

        try {
            const res = await axios.post('/api/save_contact', {
                contact_mobile: searchResult.mobile,
                nickname: nickname || searchResult.name
            });

            if (res.data.success) {
                onContactAdded();
                handleClose();
            } else {
                setError('Failed to add contact.');
            }
        } catch (err) {
            setError('Error adding contact.');
        }
    };

    const handleClose = () => {
        setMobile('');
        setSearchResult(null);
        setNickname('');
        setError('');
        onClose();
    };

    // Inline Styles
    const overlayStyle = {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1000
    };

    const modalStyle = {
        backgroundColor: '#202c33',
        padding: '20px',
        borderRadius: '10px',
        width: '90%',
        maxWidth: '400px',
        color: '#e9edef',
        boxShadow: '0 4px 6px rgba(0,0,0,0.3)'
    };

    const inputStyle = {
        width: '100%',
        padding: '10px',
        marginBottom: '10px',
        borderRadius: '5px',
        border: '1px solid #2a3942',
        backgroundColor: '#111b21',
        color: 'white',
        outline: 'none'
    };

    const buttonStyle = {
        padding: '10px 15px',
        borderRadius: '5px',
        border: 'none',
        cursor: 'pointer',
        fontWeight: 'bold',
        marginTop: '10px'
    };

    const searchBtnStyle = {
        ...buttonStyle,
        backgroundColor: '#00a884',
        color: 'white',
        width: '100%'
    };

    const addBtnStyle = {
        ...buttonStyle,
        backgroundColor: '#00a884',
        color: 'white',
        marginRight: '10px'
    };

    const cancelBtnStyle = {
        ...buttonStyle,
        backgroundColor: '#d9534f',
        color: 'white'
    };

    return (
        <div style={overlayStyle}>
            <div style={modalStyle}>
                <h2 style={{ marginTop: 0, marginBottom: '20px', textAlign: 'center' }}>Add New Contact</h2>

                {!searchResult ? (
                    <>
                        <label style={{ display: 'block', marginBottom: '5px' }}>Mobile Number:</label>
                        <input
                            type="text"
                            value={mobile}
                            onChange={(e) => setMobile(e.target.value)}
                            style={inputStyle}
                            placeholder="Enter mobile number"
                        />
                        <button onClick={handleSearch} style={searchBtnStyle} disabled={loading}>
                            {loading ? 'Searching...' : 'Search'}
                        </button>
                    </>
                ) : (
                    <>
                        <div style={{ marginBottom: '15px', padding: '10px', backgroundColor: '#111b21', borderRadius: '5px' }}>
                            <p style={{ margin: '5px 0' }}><strong>Name:</strong> {searchResult.name}</p>
                            <p style={{ margin: '5px 0' }}><strong>Mobile:</strong> {searchResult.mobile}</p>
                        </div>

                        <label style={{ display: 'block', marginBottom: '5px' }}>Nickname (Optional):</label>
                        <input
                            type="text"
                            value={nickname}
                            onChange={(e) => setNickname(e.target.value)}
                            style={inputStyle}
                            placeholder="Enter nickname"
                        />

                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <button onClick={handleAdd} style={addBtnStyle}>Add Contact</button>
                            <button onClick={() => setSearchResult(null)} style={{ ...cancelBtnStyle, backgroundColor: '#6c757d', marginRight: '10px' }}>Back</button>
                        </div>
                    </>
                )}

                {error && <p style={{ color: '#f15c6d', marginTop: '10px', textAlign: 'center' }}>{error}</p>}

                {!searchResult && (
                    <div style={{ marginTop: '15px', textAlign: 'center' }}>
                        <button onClick={handleClose} style={cancelBtnStyle}>Cancel</button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default AddContact;
