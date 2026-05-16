import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import './Auth.css'; // Reuse auth styles

const Profile = () => {
    const { user, setUser } = useAuth();
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        gender: '',
        profile_picture: null
    });
    const [preview, setPreview] = useState(null);
    const [message, setMessage] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        if (user) {
            setFormData({
                username: user.username || '',
                email: user.email || '',
                gender: user.gender || '',
                profile_picture: null
            });
            setPreview(user.profile_picture);
        }
    }, [user]);

    const handleChange = (e) => {
        const { name, value, files } = e.target;
        if (name === 'profile_picture') {
            const file = files[0];
            setFormData({ ...formData, profile_picture: file });
            setPreview(URL.createObjectURL(file));
        } else {
            setFormData({ ...formData, [name]: value });
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setMessage('');

        const data = new FormData();
        data.append('username', formData.username);
        data.append('email', formData.email);
        data.append('gender', formData.gender);
        if (formData.profile_picture) {
            data.append('profile_picture', formData.profile_picture);
        }

        try {
            const res = await axios.post('/api/profile', data, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });
            if (res.data.success) {
                setUser(res.data.user_info);
                setMessage('Profile updated successfully!');
                setTimeout(() => navigate('/teacher_dashboard'), 1500);
            }
        } catch (err) {
            setMessage('Error updating profile');
        }
    };

    return (
        <div className="auth-container">
            <div className="auth-form-container">
                <h2>Edit Profile</h2>
                {preview && (
                    <div style={{ textAlign: 'center', marginBottom: '15px' }}>
                        <img
                            src={preview}
                            alt="Profile"
                            style={{ width: '100px', height: '100px', borderRadius: '50%', objectFit: 'cover' }}
                        />
                    </div>
                )}
                <form onSubmit={handleSubmit} style={{ color: 'black' }}>
                    <label>Username:</label>
                    <input type="text" name="username" className="auth-input1" value={formData.username} onChange={handleChange} required />

                    <label>Email:</label>
                    <input type="email" name="email" className="auth-input1" value={formData.email} onChange={handleChange} />

                    <label>Gender:</label>
                    <select name="gender" className="auth-select1" value={formData.gender} onChange={handleChange} required>
                        <option value="">Select Gender</option>
                        <option value="male">Male</option>
                        <option value="female">Female</option>
                        <option value="other">Other</option>
                    </select>

                    <label>Profile Picture:</label>
                    <input type="file" name="profile_picture" className="auth-input" onChange={handleChange} />

                    {message && <div style={{ textAlign: 'center', color: message.includes('Error') ? 'red' : 'green' }}>{message}</div>}

                    <button type="submit" className="auth-button">Update Profile</button>
                    <button type="button" className="auth-button" style={{ background: '#6c757d', marginTop: '10px' }} onClick={() => navigate('/teacher_dashboard')}>Cancel</button>
                </form>
            </div>
        </div>
    );
};

export default Profile;
