import React, { createContext, useState, useEffect, useContext } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const checkAuth = async () => {
            try {
                const res = await axios.get('/api/profile');
                if (res.data.success) {
                    setUser(res.data.user_info);
                }
            } catch (error) {
                console.log("Not logged in");
            } finally {
                setLoading(false);
            }
        };
        checkAuth();
    }, []);

    const login = async (mobile, password) => {
        try {
            const res = await axios.post('/api/login', { action: 'login', mobile, password });
            if (res.data.success) {
                setUser(res.data.user);
                return { success: true };
            }
            return { success: false, message: res.data.message };
        } catch (error) {
            return { success: false, message: error.response?.data?.message || "Login failed" };
        }
    };

    const logout = async () => {
        await axios.get('/api/logout');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading, setUser }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
