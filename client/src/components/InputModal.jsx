import React from 'react';
import './ConfirmationModal.css'; // Reusing the same styles

const InputModal = ({ isOpen, title, message, value, onChange, onConfirm, onCancel, confirmText = "Confirm", cancelText = "Cancel" }) => {
    if (!isOpen) return null;

    return (
        <div className="modal-overlay">
            <div className="modal-content">
                <div className="modal-header">
                    <h3>{title}</h3>
                </div>
                <div className="modal-body">
                    <p>{message}</p>
                    <input
                        type="text"
                        value={value}
                        onChange={onChange}
                        style={{
                            width: '100%',
                            padding: '8px',
                            marginTop: '10px',
                            borderRadius: '4px',
                            border: '1px solid #ccc',
                            boxSizing: 'border-box'
                        }}
                    />
                </div>
                <div className="modal-footer">
                    <button className="modal-btn cancel-btn" onClick={onCancel}>
                        {cancelText}
                    </button>
                    <button className="modal-btn confirm-btn" onClick={onConfirm}>
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default InputModal;
