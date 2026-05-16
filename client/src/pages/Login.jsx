import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import './Auth.css';

const Login = () => {
    // Standard Login
    const [mobile, setMobile] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const { login } = useAuth();
    const navigate = useNavigate();

    // Forgot Password States
    const [isForgotPassword, setIsForgotPassword] = useState(false);
    const [forgotStep, setForgotStep] = useState(1);
    const [email, setEmail] = useState('');
    const [otp, setOtp] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [forgotError, setForgotError] = useState('');
    const [forgotSuccess, setForgotSuccess] = useState('');
    const [resetUsername, setResetUsername] = useState('');
    const [resetMobile, setResetMobile] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        const result = await login(mobile, password);
        if (result.success) {
            navigate('/teacher_dashboard');
        } else {
            setError(result.message);
        }
    };

    const handleSendOtp = async (e) => {
        e.preventDefault();
        setForgotError('');
        setForgotSuccess('');
        try {
            const res = await axios.post('/api/forgot_password/send_otp', { email });
            if (res.data.success) {
                setForgotSuccess(res.data.message);
                setForgotStep(2);
            }
        } catch (error) {
            setForgotError(error.response?.data?.message || 'Failed to send OTP.');
        }
    };

    const handleVerifyOtp = async (e) => {
        e.preventDefault();
        setForgotError('');
        setForgotSuccess('');
        try {
            const res = await axios.post('/api/forgot_password/verify_otp', { email, otp });
            if (res.data.success) {
                setForgotSuccess(res.data.message);
                setResetUsername(res.data.username);
                setResetMobile(res.data.mobile);
                setForgotStep(3);
            }
        } catch (error) {
            setForgotError(error.response?.data?.message || 'Invalid OTP.');
        }
    };

    const handleResetPassword = async (e) => {
        e.preventDefault();
        setForgotError('');
        setForgotSuccess('');

        if (newPassword !== confirmPassword) {
            setForgotError("Passwords do not match");
            return;
        }

        try {
            const res = await axios.post('/api/forgot_password/reset', { email, otp, new_password: newPassword });
            if (res.data.success) {
                setForgotSuccess("Password reset successfully. You can now login.");
                // Reset state after a short delay
                setTimeout(() => {
                    setIsForgotPassword(false);
                    setForgotStep(1);
                    setEmail('');
                    setOtp('');
                    setNewPassword('');
                    setConfirmPassword('');
                    setForgotSuccess('');
                    setResetUsername('');
                    setResetMobile('');
                }, 2000);
            }
        } catch (error) {
            setForgotError(error.response?.data?.message || 'Failed to reset password.');
        }
    };

    if (isForgotPassword) {
        return (
            <div className="auth-container">
                <div className="auth-form-container">
                    <h2>Forgot Password</h2>
                    {forgotError && <div className="auth-error">{forgotError}</div>}
                    {forgotSuccess && <div className="auth-success" style={{ color: 'green', marginBottom: '10px' }}>{forgotSuccess}</div>}

                    {forgotStep === 1 && (
                        <form onSubmit={handleSendOtp}>
                            <label>Email:</label>
                            <input
                                type="email"
                                className="auth-input"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                style={{ color: 'black', backgroundColor: 'white' }}
                                required
                            />
                            <button type="submit" className="auth-button">Send OTP</button>
                        </form>
                    )}

                    {forgotStep === 2 && (
                        <form onSubmit={handleVerifyOtp}>
                            <label>Enter OTP from Email / Server Console:</label>
                            <input
                                type="text"
                                className="auth-input"
                                value={otp}
                                onChange={(e) => setOtp(e.target.value)}
                                style={{ color: 'black', backgroundColor: 'white' }}
                                required
                            />
                            <button type="submit" className="auth-button">Verify OTP</button>
                        </form>
                    )}

                    {forgotStep === 3 && (
                        <form onSubmit={handleResetPassword}>
                            <h3 style={{ marginBottom: '15px' }}>
                                Hello, {resetUsername}! <br />
                                <span style={{ fontSize: '0.8rem', color: '#555' }}>
                                    Mobile: {resetMobile}
                                </span>
                            </h3>
                            <label>New Password:</label>
                            <input
                                type="password"
                                className="auth-input"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                style={{ color: 'black', backgroundColor: 'white' }}
                                required
                            />
                            <label>Confirm Password:</label>
                            <input
                                type="password"
                                className="auth-input"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                style={{ color: 'black', backgroundColor: 'white' }}
                                required
                            />
                            <button type="submit" className="auth-button">Reset Password</button>
                        </form>
                    )}

                    <div style={{ marginTop: '15px', textAlign: 'center' }}>
                        <button
                            onClick={() => {
                                setIsForgotPassword(false);
                                setForgotStep(1);
                                setForgotError('');
                                setForgotSuccess('');
                                setResetUsername('');
                                setResetMobile('');
                            }}
                            style={{ background: 'transparent', border: 'none', color: '#007bff', cursor: 'pointer', textDecoration: 'underline' }}
                        >
                            Back to Login
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="auth-container">
            <div className="auth-form-container">
                <h2>Login</h2>
                <form onSubmit={handleSubmit}>
                    <label htmlFor="login_mobile">Mobile Number:</label>
                    <input
                        type="text"
                        id="login_mobile"
                        className="auth-input"
                        style={{ color: 'black', backgroundColor: 'white' }}
                        value={mobile}
                        onChange={(e) => setMobile(e.target.value)}
                        required
                    />

                    <label htmlFor="login_password">Password:</label>
                    <input
                        type="password"
                        id="login_password"
                        className="auth-input"
                        style={{ color: 'black', backgroundColor: 'white' }}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                    />

                    {error && <div className="auth-error">{error}</div>}

                    <div style={{ textAlign: 'right', marginBottom: '15px' }}>
                        <button
                            type="button"
                            onClick={() => setIsForgotPassword(true)}
                            style={{ background: 'transparent', border: 'none', color: '#007bff', cursor: 'pointer', fontSize: '0.9rem' }}
                        >
                            Forgot Password?
                        </button>
                    </div>

                    <button type="submit" className="auth-button">Login</button>
                </form>

                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '15px', fontSize: '0.9rem' }}>
                    <span>Don't have an account?</span>
                    <Link to="/register" className="auth-toggle-link" style={{ marginLeft: '5px' }}>Register</Link>
                </div>
            </div>
        </div>
    );
};

export default Login;
