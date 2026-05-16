import React from 'react';
import './ImageModal.css';

const ImageModal = ({ isOpen, imageUrl, onClose }) => {
    if (!isOpen) return null;

    return (
        <div className="image-modal-overlay" onClick={onClose}>
            <div className="image-modal-content" onClick={(e) => e.stopPropagation()}>
                <img src={imageUrl} alt="Full screen" className="full-screen-image" />
                <button className="close-btn" onClick={onClose}>×</button>
            </div>
        </div>
    );
};

export default ImageModal;
