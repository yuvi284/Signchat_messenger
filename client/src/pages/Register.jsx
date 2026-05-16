import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import './Auth.css';

const Register = () => {
    const [formData, setFormData] = useState({
        username: '',
        password: '',
        mobile: '',
        email: '',
        gender: '',
        profile_picture: null,
        otp: ''
    });

    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [otpSent, setOtpSent] = useState(false);
    const [emailVerified, setEmailVerified] = useState(false);
    const navigate = useNavigate();

    const handleChange = (e) => {
        const { name, value, files } = e.target;
        if (name === 'profile_picture') {
            setFormData({ ...formData, profile_picture: files[0] });
        } else {
            setFormData({ ...formData, [name]: value });
        }
    };

    const validateMobile = (mobileString) => {
        const phonePattern = /^(\d{3})[- ]?(\d{3})[- ]?(\d{4})$/;
        const simplePhone = /^\d{10}$/;
        return simplePhone.test(mobileString) || phonePattern.test(mobileString);
    };

    const handleSendOtp = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!validateMobile(formData.mobile)) {
            setError("Please enter a valid 10-digit mobile number first.");
            return;
        }

        if (!formData.email) {
            setError("Email is required to receive an OTP.");
            return;
        }

        try {
            const res = await axios.post('/api/register/send_otp', {
                email: formData.email,
                mobile: formData.mobile
            });
            if (res.data.success) {
                setOtpSent(true);
                setSuccessMessage(res.data.message);
            }
        } catch (err) {
            setError(err.response?.data?.message || "Failed to send OTP.");
        }
    };

    const handleVerifyOtp = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!formData.otp) {
            setError("Please enter the OTP.");
            return;
        }

        try {
            const res = await axios.post('/api/register/verify_otp', {
                email: formData.email,
                otp: formData.otp
            });
            if (res.data.success) {
                setEmailVerified(true);
                setOtpSent(false); // remove otp input UI
                setSuccessMessage("Email verified successfully!");
            }
        } catch (err) {
            setError(err.response?.data?.message || "Invalid OTP.");
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!validateMobile(formData.mobile)) {
            setError("Please enter a valid 10-digit mobile number.");
            return;
        }

        if (!emailVerified) {
            setError("Please verify your email before registering.");
            return;
        }

        const data = new FormData();
        for (const key in formData) {
            data.append(key, formData[key]);
        }

        try {
            const res = await axios.post('/api/register', data, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });
            if (res.data.success) {
                alert("Registration successful. Please log in.");
                navigate('/login');
            }
        } catch (err) {
            setError(err.response?.data?.message || "Registration failed");
        }
    };

    return (
        <div className="auth-container" >
            <div className="auth-form-container" >
                <h2>Register</h2>

                {successMessage && <div className="auth-success" style={{ color: 'green', marginBottom: '10px' }}>{successMessage}</div>}

                <form onSubmit={handleSubmit}>
                    <label>Username:</label>
                    <input type="text" name="username" className="auth-input1" onChange={handleChange} required />

                    <label>Password:</label>
                    <input type="password" name="password" className="auth-input1" onChange={handleChange} required />

                    <label>Mobile Number:</label>
                    <input type="text" name="mobile" className="auth-input1" onChange={handleChange} required />

                    <label>Email:</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        <input
                            type="email"
                            name="email"
                            className="auth-input1"
                            onChange={handleChange}
                            style={{ marginBottom: '0' }}
                            required
                            disabled={otpSent || emailVerified}
                        />

                        {!emailVerified && !otpSent && (
                            <button type="button" onClick={handleSendOtp} className="auth-button" style={{ padding: '8px', marginTop: '5px' }}>
                                Send OTP
                            </button>
                        )}
                    </div>

                    {otpSent && !emailVerified && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '10px' }}>
                            <label>Enter OTP from Email:</label>
                            <input
                                type="text"
                                name="otp"
                                className="auth-input1"
                                onChange={handleChange}
                                style={{ backgroundColor: 'white', color: 'black', marginBottom: '0' }}
                                required
                            />
                            <div style={{ display: 'flex', gap: '10px', marginTop: '5px' }}>
                                <button type="button" onClick={handleVerifyOtp} className="auth-button" style={{ flex: 1, padding: '8px' }}>
                                    Verify
                                </button>
                                <button type="button" onClick={() => setOtpSent(false)} className="auth-button" style={{ flex: 1, padding: '8px', backgroundColor: 'gray' }}>
                                    Cancel
                                </button>
                            </div>
                        </div>
                    )}

                    {emailVerified && (
                        <div style={{ color: 'green', fontWeight: 'bold', marginTop: '5px', marginBottom: '10px' }}>
                            ✓ Email Verified
                        </div>
                    )}

                    <label style={{ marginTop: '10px' }}>Gender:</label>
                    <select name="gender" className="auth-select1" onChange={handleChange} required>
                        <option value="">Select Gender</option>
                        <option value="male">Male</option>
                        <option value="female">Female</option>
                        <option value="other">Other</option>
                    </select>

                    <label>Profile Picture:</label>
                    <input type="file" name="profile_picture" className="auth-input" onChange={handleChange} />

                    {error && <div className="auth-error">{error}</div>}

                    <button type="submit" className="auth-button" disabled={!emailVerified}>
                        Register
                    </button>
                </form>

                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '15px', fontSize: '0.9rem' }}>
                    <span>Already have an account?</span>
                    <Link to="/login" className="auth-toggle-link" style={{ marginLeft: '5px' }}>Login</Link>
                </div>
            </div>
        </div>
    );
};

export default Register;
