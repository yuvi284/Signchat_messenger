import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { FaPhoneAlt, FaVideo, FaArrowLeft, FaVolumeUp } from 'react-icons/fa';
import { MdGTranslate } from "react-icons/md";
import ConfirmationModal from './ConfirmationModal';
import InputModal from './InputModal';
import ImageModal from './ImageModal';
import PredictionMatrixModal from './PredictionMatrixModal';
import './ChatArea.css';
import { BsThreeDotsVertical } from "react-icons/bs";
import ExpandMsgModal from './expandMsgModal';
import { io } from "socket.io-client";

const ENDPOINT = window.location.origin; // Adapts to current host:port
var socket;
const ChatArea = ({ contact, currentUser, onBack, onMessageUpdate }) => {
    const [messages, setMessages] = useState([]);
    const [inputText, setInputText] = useState('');
    const [contactImage, setContactImage] = useState('/images/default_user.png');
    const chatHistoryRef = useRef(null);

    // ISL Video State
    const [isVideoMode, setIsVideoMode] = useState(false);
    const [videoPlaylist, setVideoPlaylist] = useState([]);
    const [currentVideoIndex, setCurrentVideoIndex] = useState(0);
    const [activePlayer, setActivePlayer] = useState(1);
    const videoRef1 = useRef(null);
    const videoRef2 = useRef(null);
    const clipLimitRef = useRef(null);
    const [vCurrentTime, setVCurrentTime] = useState(0);
    const [vDuration, setVDuration] = useState(0);
    const [vIsPlaying, setVIsPlaying] = useState(true);

    // Camera State
    const [isCameraOpen, setIsCameraOpen] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const [recordedChunks, setRecordedChunks] = useState([]);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [mediaRecorder, setMediaRecorder] = useState(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const cameraVideoRef = useRef(null);
    const streamRef = useRef(null);
    const shouldUploadRef = useRef(false); // Track if we should upload after stopping
    const recordingTimerRef = useRef(null);
    const [recordingTime, setRecordingTime] = useState(0);
    const [capturedFrames, setCapturedFrames] = useState(null);

    // Speech Recognition State
    const [isListening, setIsListening] = useState(false);
    const [selectedLanguage, setSelectedLanguage] = useState('hi-IN');

    // Modal State
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [messageToDelete, setMessageToDelete] = useState(null);

    // Menu & New Feature State
    const [showMenu, setShowMenu] = useState(false);
    const [showClearChatModal, setShowClearChatModal] = useState(false);
    const [showChangeNameModal, setShowChangeNameModal] = useState(false);
    const [newName, setNewName] = useState('');
    const [showImageModal, setShowImageModal] = useState(false);

    // Prediction Modal State
    const [isPredictionModalOpen, setIsPredictionModalOpen] = useState(false);
    const [predictionData, setPredictionData] = useState(null);
    const [currentFullSentence, setCurrentFullSentence] = useState('');

    // Test Model Modal State
    const [showTestModelModal, setShowTestModelModal] = useState(false);
    const [testModelResult, setTestModelResult] = useState('');
    const [gestureData, setGestureData] = useState(null);
    // Expand Message Modal State
    const [showExpandMsgModal, setShowExpandMsgModal] = useState(false);
    const [expandedMsg, setExpandedMsg] = useState('');
    const [expandedMsgIndex, setExpandedMsgIndex] = useState(null);
    const [translatedMessages, setTranslatedMessages] = useState({}); // Stores translated text by messageId
    const [speakingMessageId, setSpeakingMessageId] = useState(null);

    // State for scroll management
    const [isFirstLoad, setIsFirstLoad] = useState(true);
    const lastMessagesStrRef = useRef("[]");

    useEffect(() => {
        if (contact) {
            fetchMessages();
            fetchContactImage();

            // Reset state for new contact
            setIsFirstLoad(true);
            lastMessagesStrRef.current = "[]";
            setMessages([]);

            // Mark as seen and then refresh contacts to update badges
            const markSeenAndRefresh = async () => {
                try {
                    await axios.post('/api/mark_seen', { contact_mobile: contact.mobile });
                    if (onMessageUpdate) onMessageUpdate();
                } catch (error) {
                    console.error("Error marking messages as seen", error);
                }
            };
            markSeenAndRefresh();

            // Reset video mode on contact change
            exitVideoMode();
            closeCamera(); // Also close camera if open

            // Initialize Socket.IO
            socket = io(ENDPOINT);
            socket.emit("join", { mobile: currentUser.mobile });

            socket.on("receive_message", (newMessage) => {
                // Check if the message belongs to the current chat
                if (newMessage.sender_mobile === contact.mobile || newMessage.receiver_mobile === contact.mobile) {
                    setMessages((prevMessages) => [...prevMessages, newMessage]);
                    // If it's from the contact, mark as seen
                    if (newMessage.sender_mobile === contact.mobile) {
                        axios.post('/api/mark_seen', { contact_mobile: contact.mobile });
                    }
                }
                // Notify parent (for sidebar badges, etc.) in any case
                if (onMessageUpdate) onMessageUpdate();
            });

            return () => {
                socket.disconnect();
            };
        }
    }, [contact, currentUser.mobile]);

    useEffect(() => {
        if (chatHistoryRef.current && !isVideoMode && !isCameraOpen) {
            // Smart Scroll Logic for new messages
            const { scrollTop, scrollHeight, clientHeight } = chatHistoryRef.current;
            const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;

            if (isFirstLoad || isNearBottom) {
                chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
                if (messages.length > 0) setIsFirstLoad(false);
            }
        }
    }, [messages]);

    useEffect(() => {
        // When switching back to chat view (from camera/video), scroll to bottom
        if (chatHistoryRef.current && !isVideoMode && !isCameraOpen) {
            chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
        }
    }, [isVideoMode, isCameraOpen]);

    // ... (existing effects for video/camera) ...

    const fetchMessages = async () => {
        try {
            const res = await axios.get(`/api/get_messages?contact=${contact.mobile}`);
            const msgs = res.data.messages || [];

            // Convert to string to compare content equality
            const currentMsgsStr = JSON.stringify(msgs);

            // Only update state if the messages have actually changed
            if (currentMsgsStr !== lastMessagesStrRef.current) {
                setMessages(msgs);
                lastMessagesStrRef.current = currentMsgsStr;

                // Check if there are any unread messages from the other person
                const hasUnread = msgs.some(msg => msg.sender_mobile === contact.mobile && msg.seen === 0);

                if (hasUnread) {
                    // Mark them as seen in the background
                    await axios.post('/api/mark_seen', { contact_mobile: contact.mobile });
                    // Refresh the sidebar/badges if the callback is provided
                    if (onMessageUpdate) onMessageUpdate();
                }
            }

        } catch (error) {
            console.error("Error fetching messages", error);
        }
    };

    const fetchContactImage = async () => {
        try {
            const res = await axios.get(`/api/get_contact_image?mobile=${contact.mobile}`);
            setContactImage(res.data.profile_picture);
        } catch (error) {
            console.error("Error fetching image", error);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const sendMessage = async () => {
        if (!inputText.trim()) return;
        try {
            const res = await axios.post('/api/send-message', {
                receiver_mobile: contact.mobile,
                message: inputText,
                gesture_data: gestureData
            });
            if (res.data.success) {
                setInputText('');
                fetchMessages();
                setGestureData(null);
                if (onMessageUpdate) onMessageUpdate(); // Trigger update
            }
        } catch (error) {
            console.error("Error sending message", error);
        }
    };

    const handleDeleteClick = (messageId) => {
        setMessageToDelete(messageId);
        setIsDeleteModalOpen(true);
    };

    const confirmDeleteMessage = async () => {
        if (!messageToDelete) return;
        try {
            const res = await axios.post('/api/delete_message', { message_id: messageToDelete });
            if (res.data.success) {
                fetchMessages();
                if (onMessageUpdate) onMessageUpdate(); // Trigger update
            }
        } catch (error) {
            console.error("Error deleting message", error);
        } finally {
            setIsDeleteModalOpen(false);
            setMessageToDelete(null);
        }
    };

    const playISL = async (text) => {
        try {
            const res = await axios.post('/api/convert_to_isl', { text });
            if (res.data.videos && res.data.videos.length > 0) {
                setVideoPlaylist(res.data.videos);
                setCurrentVideoIndex(0);
                setActivePlayer(1);
                setIsVideoMode(true);
            } else {
                alert("No ISL video found for this text.");
            }
        } catch (error) {
            console.error("ISL conversion failed", error);
            alert("Failed to convert to ISL");
        }
    };

    const handleLoadedMetadata = (e) => {
        const video = e.target;
        if ((activePlayer === 1 && video === videoRef1.current) ||
            (activePlayer === 2 && video === videoRef2.current)) {
            let duration = video.duration;
            // Play only first 6 sec if video is between 6 and 50 seconds
            if (duration > 6 && duration < 50) {
                clipLimitRef.current = 6;
                setVDuration(6);
            } else {
                clipLimitRef.current = null;
                setVDuration(duration);
            }
            setVIsPlaying(true);
        }
    };

    const handleTimeUpdate = (e) => {
        const video = e.target;
        if ((activePlayer === 1 && video === videoRef1.current) ||
            (activePlayer === 2 && video === videoRef2.current)) {
            setVCurrentTime(video.currentTime);

            if (clipLimitRef.current && video.currentTime >= clipLimitRef.current) {
                handleVideoEnded();
            }
        }
    };

    const handleVideoEnded = () => {
        clipLimitRef.current = null; // Reset limit for next video
        setVCurrentTime(0);
        if (currentVideoIndex < videoPlaylist.length - 1) {
            setCurrentVideoIndex(prev => prev + 1);
            setActivePlayer(prev => (prev === 1 ? 2 : 1));
        } else {
            exitVideoMode();
        }
    };

    useEffect(() => {
        if (isVideoMode) {
            const activeRef = activePlayer === 1 ? videoRef1.current : videoRef2.current;
            if (activeRef) {
                activeRef.currentTime = 0;
                activeRef.play().catch(e => console.error("Error playing active video:", e));
            }
        }
    }, [currentVideoIndex, activePlayer, isVideoMode]);

    const togglePlayPause = () => {
        const activeRef = activePlayer === 1 ? videoRef1.current : videoRef2.current;
        if (activeRef) {
            if (activeRef.paused) {
                activeRef.play();
                setVIsPlaying(true);
            } else {
                activeRef.pause();
                setVIsPlaying(false);
            }
        }
    };

    const formatTime = (time) => {
        const minutes = Math.floor(time / 60);
        const seconds = Math.floor(time % 60);
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    };

    const exitVideoMode = () => {
        setIsVideoMode(false);
        setVideoPlaylist([]);
        setCurrentVideoIndex(0);
    };

    // Camera Functions
    const openCamera = async () => {
        setIsCameraOpen(true);
        setPreviewUrl(null);
        setRecordedChunks([]);
        setCapturedFrames(null);
        shouldUploadRef.current = false;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640, max: 640 },
                    height: { ideal: 480, max: 480 },
                    frameRate: { min: 11, ideal: 13, max: 15 }
                },
                audio: false
            });
            const audioTracks = stream.getAudioTracks();
            const videoTrack = stream.getVideoTracks()[0];
            console.log(`[VideoConfig] audio_tracks=${audioTracks.length}`);
            if (videoTrack) {
                console.log("[VideoConfig] video_settings=", videoTrack.getSettings());
            }
            streamRef.current = stream;
            if (cameraVideoRef.current) {
                cameraVideoRef.current.srcObject = stream;
            }
        } catch (error) {
            console.error("Error accessing camera:", error);
            alert("Could not access camera. Please ensure you have granted permissions.");
            setIsCameraOpen(false);
        }
    };

    const closeCamera = () => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
        if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
        setIsCameraOpen(false);
        setIsRecording(false);
        setPreviewUrl(null);
        setRecordedChunks([]);
    };

    const toggleRecording = () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    };

    const startRecording = () => {
        if (!streamRef.current) return;
        const media = new MediaRecorder(streamRef.current, {
            mimeType: 'video/webm',
            videoBitsPerSecond: 700000
        });
        console.log("[VideoConfig] recorder_options=", {
            mimeType: media.mimeType,
            videoBitsPerSecond: 700000,
            audioTracks: streamRef.current.getAudioTracks().length
        });
        setMediaRecorder(media);
        const chunks = [];
        shouldUploadRef.current = false;

        media.ondataavailable = (e) => {
            if (e.data.size > 0) {
                chunks.push(e.data);
            }
        };

        media.onstop = () => {
            const blob = new Blob(chunks, { type: 'video/webm' });

            if (shouldUploadRef.current) {
                // Determine if we need to set the preview URL or just process immediately.
                // Since we want immediate conversion, we might skip setting preview URL to state
                // if it causes re-renders that interfere, but for now we play safe.
                const url = URL.createObjectURL(blob);
                setPreviewUrl(url);
                setRecordedChunks(chunks);

                // Directly process the video blob
                processVideoBlob(blob);
            } else {
                // Just stopped without converting (e.g. close)
                const url = URL.createObjectURL(blob);
                setPreviewUrl(url);
                setRecordedChunks(chunks);
            }
        };

        media.start();
        setIsRecording(true);
        setRecordingTime(0);

        const startTime = Date.now();
        recordingTimerRef.current = setInterval(() => {
            const elapsed = (Date.now() - startTime) / 1000;
            if (elapsed >= 4.0) {
                setRecordingTime(4.0);
                clearInterval(recordingTimerRef.current);
            } else {
                setRecordingTime(elapsed);
            }
        }, 100);

        // Automatically stop recording after 4 seconds and process it
        setTimeout(() => {
            if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
            if (media.state !== 'inactive') {
                shouldUploadRef.current = true;
                media.stop();
                setIsRecording(false);
            }
        }, 4000);
    };

    const handleStopAndConvert = () => {
        if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            shouldUploadRef.current = true;
            mediaRecorder.stop();
            setIsRecording(false);
        }
    };

    const processVideoBlob = async (blob) => {
        setIsProcessing(true);
        const formData = new FormData();
        formData.append('video', blob, 'recorded_video.webm');
        const uploadStart = performance.now();
        console.log(`[Timing][VideoUpload] camera_blob_size=${(blob.size / 1024).toFixed(1)}KB`);

        try {
            const res = await axios.post('/api/process_uploaded_video', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            console.log(`[Timing][VideoUpload] camera_total_request=${((performance.now() - uploadStart) / 1000).toFixed(3)}s`);
            if (res.data.frames) {
                console.log(`Number of frames captured: ${res.data.frames}`);
                setCapturedFrames(res.data.frames);
                // Also show it briefly via alert or toast if user expects to "see" it printed
                // But a console log handles "print the number of frames" well.
            }
            if (res.data.sentence) {
                setInputText(res.data.sentence);
                if (res.data.raw_data) {
                    setGestureData(res.data.raw_data);
                }
                closeCamera();
            } else {
                alert("No sentence detected.");
            }
        } catch (error) {
            console.log(`[Timing][VideoUpload] camera_failed_after=${((performance.now() - uploadStart) / 1000).toFixed(3)}s`);
            console.error("Error processing video:", error);
            alert("Failed to process video.");
        } finally {
            setIsProcessing(false);
        }
    };

    const stopRecording = () => {
        if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            setIsRecording(false);
        }
    };

    const sendVideo = async () => {
        if (recordedChunks.length === 0) return;
        setIsProcessing(true);
        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const formData = new FormData();
        formData.append('video', blob, 'recorded_video.webm');
        const uploadStart = performance.now();
        console.log(`[Timing][VideoUpload] manual_send_blob_size=${(blob.size / 1024).toFixed(1)}KB`);

        try {
            const res = await axios.post('/api/process_uploaded_video', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            console.log(`[Timing][VideoUpload] manual_send_total_request=${((performance.now() - uploadStart) / 1000).toFixed(3)}s`);
            if (res.data.frames) {
                console.log(`Number of frames captured: ${res.data.frames}`);
            }
            if (res.data.sentence) {
                setInputText(res.data.sentence);
                if (res.data.raw_data) {
                    setGestureData(res.data.raw_data);
                }
                closeCamera();
            } else {
                alert("No sentence detected.");
            }
        } catch (error) {
            console.log(`[Timing][VideoUpload] manual_send_failed_after=${((performance.now() - uploadStart) / 1000).toFixed(3)}s`);
            console.error("Error processing video:", error);
            alert("Failed to process video.");
        } finally {
            setIsProcessing(false);
        }
    };

    // Speech Recognition
    const handleSpeak = () => {
        if (!('webkitSpeechRecognition' in window)) {
            alert("Speech recognition is not supported in this browser. Please use Chrome.");
            return;
        }

        const recognition = new window.webkitSpeechRecognition();
        recognition.lang = selectedLanguage;
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = () => {
            setIsListening(true);
        };

        recognition.onend = () => {
            setIsListening(false);
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            setInputText(prev => prev + (prev ? ' ' : '') + transcript);
        };

        recognition.onerror = (event) => {
            console.error("Speech recognition error", event.error);
            setIsListening(false);
        };

        recognition.start();
    };


    const handleTranslateClick = async (messageId) => {
        // Toggle logic: If already showing translation, revert to original
        if (translatedMessages[messageId]) {
            const newTranslations = { ...translatedMessages };
            delete newTranslations[messageId];
            setTranslatedMessages(newTranslations);
            return;
        }

        try {
            const res = await axios.get(`/api/translate_message?message_id=${messageId}`);
            const translatedText = res.data.translated_text;
            setTranslatedMessages(prev => ({
                ...prev,
                [messageId]: translatedText
            }));
        } catch (error) {
            console.error("Error translating message:", error);
            alert("Failed to translate message.");
        }
    };

    const handleSpeakMessage = async (messageId, text) => {
        if (!('speechSynthesis' in window)) {
            alert("Text-to-speech is not supported in this browser.");
            return;
        }

        let messageText = typeof text === 'string' ? text.trim() : '';
        if (!messageText) {
            return;
        }

        // Toggle off if the same message is already speaking.
        if (speakingMessageId === messageId && window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
            setSpeakingMessageId(null);
            return;
        }

        window.speechSynthesis.cancel();

        let speechLanguage = selectedLanguage;
        try {
            const res = await axios.post('/api/translate_text', {
                text: messageText,
                target: 'hi'
            });

            if (res.data?.translated_text) {
                messageText = res.data.translated_text;
                speechLanguage = 'hi-IN';
            }
        } catch (error) {
            console.error("Error preparing speech text:", error);
        }

        const utterance = new SpeechSynthesisUtterance(messageText);
        utterance.lang = speechLanguage;
        utterance.rate = 0.82;
        utterance.pitch = 1;
        utterance.onend = () => setSpeakingMessageId(null);
        utterance.onerror = () => setSpeakingMessageId(null);

        setSpeakingMessageId(messageId);
        window.speechSynthesis.speak(utterance);
    };

    // Video Upload Handler
    const fileInputRef = useRef(null);

    const handleTestModel = async () => {
        try {
            console.log("Calling /api/test_model...");
            const res = await axios.post('/api/test_model');

            if (res.data.success) {
                // 1. Show the text to the user
                setInputText(res.data.success);

                // 2. CAPTURE THE HIDDEN DATA (Critical Step)
                // We store the raw list in memory so it's safe from other users
                if (res.data.raw_data) {
                    setGestureData(res.data.raw_data);
                }

                console.log("Test Model Result:", res.data.success);
                setTestModelResult("Model Output: " + res.data.success);
                setShowTestModelModal(true);
            } else {
                console.error("Test Model failed or returned no data");
            }
        } catch (error) {
            console.error("Error calling test_model API", error);
            alert("Error calling test_model API");
        }
    };

    const handleFileUpload = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        setIsProcessing(true);
        const formData = new FormData();
        formData.append('video', file);
        const uploadStart = performance.now();
        console.log(`[Timing][VideoUpload] file_upload_size=${(file.size / 1024).toFixed(1)}KB name=${file.name}`);

        try {
            const res = await axios.post('/api/process_uploaded_video', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            console.log(`[Timing][VideoUpload] file_upload_total_request=${((performance.now() - uploadStart) / 1000).toFixed(3)}s`);
            if (res.data.sentence) {
                setInputText(res.data.sentence);
                // Capture raw data for matrix view
                if (res.data.raw_data) {
                    setGestureData(res.data.raw_data);
                }
            } else {
                alert("No sentence detected.");
            }
        } catch (error) {
            console.log(`[Timing][VideoUpload] file_upload_failed_after=${((performance.now() - uploadStart) / 1000).toFixed(3)}s`);
            console.error("Error uploading video:", error);
            alert("Failed to upload/process video.");
        } finally {
            setIsProcessing(false);
            if (fileInputRef.current) {
                fileInputRef.current.value = ''; // Reset input
            }
        }
    };

    // New Feature Handlers
    const handleClearChat = async () => {
        try {
            const res = await axios.post('/api/delete_contact_messages', { mobile: contact.mobile });
            if (res.data.success) {
                setMessages([]);
                if (onMessageUpdate) onMessageUpdate();
            }
        } catch (error) {
            console.error("Error clearing chat", error);
        } finally {
            setShowClearChatModal(false);
            setShowMenu(false);
        }
    };

    const handleChangeName = async () => {
        if (!newName.trim()) return;
        try {
            const res = await axios.post('/api/edit_contact_name', { mobile: contact.mobile, new_name: newName });
            if (res.data.success) {
                // Ideally, we should update the contact object in the parent or re-fetch contacts
                // For now, we can reload the page or trigger a callback if available
                if (onMessageUpdate) onMessageUpdate();
                window.location.reload(); // Simple way to refresh contact name everywhere
            }
        } catch (error) {
            console.error("Error changing name", error);
        } finally {
            setShowChangeNameModal(false);
            setShowMenu(false);
        }
    };

    const openExpandMsgModal = (messageId) => {
        const msg = messages.find(m => m.message_id === messageId);
        if (!msg) return;

        let data = "No details available";
        try {
            if (msg.message_metadata) {
                if (typeof msg.message_metadata === 'string') {
                    data = JSON.parse(msg.message_metadata);
                } else {
                    data = msg.message_metadata;
                }
            }
        } catch (e) {
            data = String(msg.message_metadata);
        }

        setExpandedMsg(data);
        setShowExpandMsgModal(true);
    };

    const getRenderableMessage = (content) => {
        try {
            // Attempt to parse JSON if it starts with [
            if (content && typeof content === 'string' && content.trim().startsWith('[')) {
                const data = JSON.parse(content);
                if (Array.isArray(data)) {
                    // It is our prediction format
                    // Construct the sentence
                    const sentence = data.map(item => item.word).join(' ');
                    return { text: sentence, isMatrix: true, rawData: data };
                }
            }
        } catch (e) {
            // Not JSON or invalid format, treat as plain text
        }
        return { text: content, isMatrix: false };
    };

    if (!contact) return <div className="welcome-message">Select a contact to start chatting</div>;

    return (
        <div className="chat-area">
            <div className="chat-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'white', fontSize: '1.2rem', cursor: 'pointer' }} className="back-btn">
                        <FaArrowLeft />
                    </button>
                    <img
                        src={contactImage}
                        alt="DP"
                        style={{ width: '36px', height: '36px', borderRadius: '50%', objectFit: 'cover', cursor: 'pointer' }}
                        onClick={() => setShowImageModal(true)}
                    />
                    <div>
                        <div style={{ fontWeight: 'bold' }}>{contact.name}</div>
                        <div style={{ fontSize: '0.8rem', color: '#ccc' }}>{contact.mobile}</div>
                    </div>
                </div>
                <div className="header-actions" style={{ position: 'relative' }}>
                    {/* <FaPhoneAlt />
                    <FaVideo /> */}
                    <BsThreeDotsVertical onClick={() => setShowMenu(!showMenu)} style={{ cursor: 'pointer', fontWeight: 'bold' }} />
                    {showMenu && (
                        <div className="menu-dropdown">
                            <div className="menu-item" onClick={() => { setShowClearChatModal(true); setShowMenu(false); }}>Clear Chat</div>
                            <div className="menu-item" onClick={() => { setNewName(contact.name || contact.nickname); setShowChangeNameModal(true); setShowMenu(false); }}>Change Name</div>
                        </div>
                    )}
                </div>
            </div>

            <div className="chat-history" ref={chatHistoryRef}>
                {isVideoMode ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', paddingLeft: '60px', position: 'relative' }}>
                        <div style={{ position: 'relative', width: '100%', maxHeight: '80%', display: 'flex', flexDirection: 'column' }}>
                            <video
                                ref={videoRef1}
                                src={activePlayer === 1 ? videoPlaylist[currentVideoIndex] : (videoPlaylist[currentVideoIndex + 1] || '')}
                                autoPlay={activePlayer === 1}
                                muted
                                preload="auto"
                                style={{ width: '100%', maxHeight: '100%', margin: 'auto', borderRadius: '8px', display: activePlayer === 1 ? 'block' : 'none' }}
                                onEnded={handleVideoEnded}
                                onLoadedMetadata={handleLoadedMetadata}
                                onTimeUpdate={handleTimeUpdate}
                                onClick={togglePlayPause}
                            />
                            <video
                                ref={videoRef2}
                                src={activePlayer === 2 ? videoPlaylist[currentVideoIndex] : (videoPlaylist[currentVideoIndex + 1] || '')}
                                autoPlay={activePlayer === 2}
                                muted
                                preload="auto"
                                style={{ width: '100%', maxHeight: '100%', margin: 'auto', borderRadius: '8px', display: activePlayer === 2 ? 'block' : 'none' }}
                                onEnded={handleVideoEnded}
                                onLoadedMetadata={handleLoadedMetadata}
                                onTimeUpdate={handleTimeUpdate}
                                onClick={togglePlayPause}
                            />

                            {/* Custom Premium Controls */}
                            <div style={{
                                position: 'absolute',
                                bottom: '0',
                                left: '0',
                                right: '0',
                                background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
                                padding: '15px',
                                borderBottomLeftRadius: '8px',
                                borderBottomRightRadius: '8px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '8px'
                            }}>
                                <div style={{
                                    width: '100%',
                                    height: '4px',
                                    background: 'rgba(255,255,255,0.2)',
                                    borderRadius: '2px',
                                    position: 'relative',
                                    cursor: 'pointer'
                                }}
                                    onClick={(e) => {
                                        const activeRef = activePlayer === 1 ? videoRef1.current : videoRef2.current;
                                        if (activeRef) {
                                            const rect = e.currentTarget.getBoundingClientRect();
                                            const pos = (e.clientX - rect.left) / rect.width;
                                            const targetTime = pos * vDuration;
                                            activeRef.currentTime = targetTime;
                                        }
                                    }}>
                                    <div style={{
                                        position: 'absolute',
                                        left: 0,
                                        top: 0,
                                        height: '100%',
                                        width: `${(vCurrentTime / vDuration) * 100}%`,
                                        background: '#5cb85c',
                                        borderRadius: '2px',
                                        transition: 'width 0.1s linear'
                                    }} />
                                </div>

                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'white', fontSize: '0.9rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                                        <button onClick={togglePlayPause} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', fontSize: '1.1rem' }}>
                                            {vIsPlaying ? '⏸' : '▶'}
                                        </button>
                                        <span>{formatTime(vCurrentTime)} / {formatTime(vDuration)}</span>
                                    </div>
                                    <div style={{ fontSize: '0.8rem', opacity: 0.8 }}>
                                        Word {currentVideoIndex + 1} of {videoPlaylist.length}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <button
                            onClick={exitVideoMode}
                            style={{
                                marginTop: '20px',
                                padding: '10px 25px',
                                background: '#d9534f',
                                color: 'white',
                                border: 'none',
                                borderRadius: '25px',
                                cursor: 'pointer',
                                fontWeight: 'bold',
                                boxShadow: '0 4px 15px rgba(217, 83, 79, 0.3)',
                                transition: 'transform 0.2s',
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.05)'}
                            onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
                        >
                            Exit Video Mode
                        </button>
                    </div>
                ) : isCameraOpen ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', overflow: 'hidden', paddingLeft: '60px' }}>
                        {previewUrl ? (
                            <div style={{ position: 'relative', width: '100%', flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <video
                                    key={previewUrl}
                                    src={previewUrl}
                                    controls
                                    autoPlay
                                    style={{ maxWidth: '100%', maxHeight: '100%' }}
                                />
                                {isProcessing && (
                                    <div style={{
                                        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                                        background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white'
                                    }}>
                                        Processing...
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div style={{ width: '100%', flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                                <video
                                    ref={cameraVideoRef}
                                    autoPlay
                                    muted
                                    style={{ maxWidth: '100%', maxHeight: '100%', transform: 'scaleX(-1)' }}
                                />
                                {isRecording && (
                                    <div style={{
                                        position: 'absolute',
                                        top: '20px',
                                        left: '20px',
                                        color: '#00ff00',
                                        fontFamily: 'monospace',
                                        fontSize: '1.2rem',
                                        textShadow: '1px 1px 2px black',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        gap: '5px'
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ff0000', fontWeight: 'bold' }}>
                                            <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#ff0000', animation: 'blink 1s infinite' }} />
                                            REC
                                        </div>
                                        <div>Time: {recordingTime.toFixed(1)} / 4.0s</div>
                                    </div>
                                )}
                            </div>
                        )}

                        <div style={{ marginTop: '10px', marginBottom: '10px', display: 'flex', gap: '10px', flexShrink: 0 }}>
                            {!isRecording ? (
                                <button
                                    onClick={startRecording}
                                    style={{
                                        padding: '10px 20px',
                                        background: '#5cb85c',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '5px',
                                        cursor: 'pointer'
                                    }}
                                >
                                    🎥 Start Recording
                                </button>
                            ) : (
                                <button
                                    onClick={handleStopAndConvert}
                                    disabled={isProcessing}
                                    style={{
                                        padding: '10px 20px',
                                        background: '#5cb85c',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '5px',
                                        cursor: 'pointer',
                                        opacity: isProcessing ? 0.7 : 1
                                    }}
                                >
                                    🔄 Convert to ISL
                                </button>
                            )}
                            <button
                                onClick={closeCamera}
                                style={{
                                    padding: '10px 20px',
                                    background: '#777',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '5px',
                                    cursor: 'pointer'
                                }}
                            >
                                ❌ Close
                            </button>
                        </div>
                    </div>
                ) : (
                    messages.length === 0 ? (
                        <div style={{ textAlign: 'center', margin: 'auto', color: 'black' }}>
                            <h3>No messages yet</h3>
                        </div>
                    ) : (
                        messages.map((msg) => {
                            const renderable = getRenderableMessage(msg.message_content);
                            // If we have a translation, show it, otherwise show existing logic
                            const contentToDisplay = translatedMessages[msg.message_id]
                                ? translatedMessages[msg.message_id]
                                : renderable.text;

                            return (
                                <div key={msg.message_id} className={`chat-message ${msg.sender_mobile === currentUser.mobile ? 'sent' : 'received'}`}>
                                    <div>
                                        {contentToDisplay}
                                        {renderable.isMatrix && !translatedMessages[msg.message_id] && (
                                            <button
                                                style={{
                                                    marginLeft: '10px',
                                                    padding: '2px 8px',
                                                    fontSize: '0.75rem',
                                                    background: '#eee',
                                                    border: '1px solid #ccc',
                                                    borderRadius: '4px',
                                                    cursor: 'pointer',
                                                    color: '#333'
                                                }}
                                                onClick={() => {
                                                    setPredictionData(renderable.rawData);
                                                    setCurrentFullSentence(renderable.text);
                                                    setIsPredictionModalOpen(true);
                                                }}
                                            >
                                                Expand
                                            </button>
                                        )}
                                    </div>
                                    <div className="message-meta">
                                        <span>{msg.created_at}</span>
                                        {msg.sender_mobile === currentUser.mobile && (
                                            <span style={{ marginLeft: '5px' }}>{msg.seen === 1 ? '✓✓' : '✓'}</span>
                                        )}
                                    </div>
                                    <div className="message-actions">
                                        <button className="message-action-btn" style={{ background: '#d9534f' }} onClick={() => handleDeleteClick(msg.message_id)}>🗑️</button>
                                        <button className="message-action-btn" style={{ background: '#5cb85c' }} onClick={() => playISL(renderable.text)}>▶️</button>
                                        <button
                                            className="message-action-btn"
                                            style={{ background: speakingMessageId === msg.message_id ? '#f0ad4e' : '#0275d8' }}
                                            onClick={() => handleSpeakMessage(msg.message_id, contentToDisplay)}
                                            title={speakingMessageId === msg.message_id ? 'Stop audio' : 'Play audio'}
                                        >
                                            <FaVolumeUp />
                                        </button>
                                        <button className="message-action-btn" onClick={() => handleTranslateClick(msg.message_id)}><MdGTranslate /></button>
                                        {/*<button onClick={() => openExpandMsgModal(msg.message_id)}>E</button>*/}
                                    </div>
                                </div>
                            );
                        })
                    )
                )}
            </div>

            <div className="chat-input-container">
                {capturedFrames && (
                    <div style={{ color: '#5cb85c', fontSize: '0.85rem', marginBottom: '5px', fontWeight: 'bold' }}>
                        ✅ Video processed successfully ({capturedFrames} frames)
                    </div>
                )}
                <div className="chat-input-actions">
                    <select value={selectedLanguage} onChange={(e) => setSelectedLanguage(e.target.value)}>
                        <option value="hi-IN">Hindi</option>
                        <option value="en-US">English</option>
                    </select>
                    <button onClick={handleSpeak} style={{ background: isListening ? '#d9534f' : '' }}>
                        {isListening ? '🛑 Listening...' : '🎤 Speak'}
                    </button>
                    {/* <button className="send-btn" onClick={sendMessage}>Send</button> */}
                    <button onClick={isCameraOpen ? closeCamera : openCamera}>
                        {isCameraOpen ? '❌ Close Camera' : '📷 Camera'}
                    </button>
                    {/* <button onClick={handleTestModel}>
                        test_model
                    </button> */}

                </div>
                <div style={{ display: 'flex', alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' }}>
                    <textarea
                        rows="2"
                        placeholder="Type a message..."
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        onKeyDown={handleKeyDown}
                    ></textarea>

                    <button className="send-btn" onClick={sendMessage}>Send</button>
                </div>

            </div>

            <ConfirmationModal
                isOpen={isDeleteModalOpen}
                title="Delete Message"
                message="Are you sure you want to delete this message?"
                onConfirm={confirmDeleteMessage}
                onCancel={() => setIsDeleteModalOpen(false)}
                confirmText="Delete"
                cancelText="Cancel"
            />

            <ConfirmationModal
                isOpen={showClearChatModal}
                title="Clear Chat"
                message="Are you sure you want to clear this chat? This action cannot be undone."
                onConfirm={handleClearChat}
                onCancel={() => setShowClearChatModal(false)}
                confirmText="Clear"
                cancelText="Cancel"
            />

            <InputModal
                isOpen={showChangeNameModal}
                title="Change Contact Name"
                message="Enter the new name for this contact:"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onConfirm={handleChangeName}
                onCancel={() => setShowChangeNameModal(false)}
                confirmText="Save"
                cancelText="Cancel"
            />

            <ImageModal
                isOpen={showImageModal}
                imageUrl={contactImage}
                onClose={() => setShowImageModal(false)}
            />

            <PredictionMatrixModal
                isOpen={isPredictionModalOpen}
                onClose={() => setIsPredictionModalOpen(false)}
                data={predictionData}
                fullSentence={currentFullSentence}
            />

            <ExpandMsgModal
                isOpen={showTestModelModal}
                title="Test Model Result"
                message={testModelResult}
                onConfirm={() => setShowTestModelModal(false)}
                onCancel={() => setShowTestModelModal(false)}
                confirmText="OK"
                cancelText="Close"
            />

            <ExpandMsgModal
                isOpen={showExpandMsgModal}
                title="Expanded Message"
                message={expandedMsg} // We will just show stringified for now if not formatted
                onConfirm={() => setShowExpandMsgModal(false)}
                onCancel={() => setShowExpandMsgModal(false)}
                confirmText="OK"
                cancelText="Close"
            />
        </div>
    );
};

export default ChatArea;
