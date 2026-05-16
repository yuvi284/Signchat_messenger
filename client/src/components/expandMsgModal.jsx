import React from 'react';
import './expandMsgModal.css';

const ExpandMsgModal = ({ isOpen, title, message, onConfirm, onCancel, confirmText = "Confirm", cancelText = "Cancel" }) => {
    if (!isOpen) return null;

    const renderContent = () => {
        if (Array.isArray(message)) {
            return (
                <div className="prediction-grid">
                    {message.map((wordGroup, colIndex) => (
                        <div key={colIndex} className="prediction-column">
                            <div className="column-header">Word {colIndex + 1}</div>
                            {wordGroup.map((candidate, rowIndex) => (
                                <div key={rowIndex} className={`candidate-row ${rowIndex === 0 ? 'top-candidate' : ''}`}>
                                    <span className="candidate-word">{candidate.word}</span>
                                    <span className="candidate-conf">({(candidate.confidence * 100).toFixed(0)}%)</span>
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            );
        }
        return <p>{String(message)}</p>;
    };

    return (
        <div className="modal-overlay" onClick={onCancel}>
            <div className="modal-content dark-theme" onClick={(e) => e.stopPropagation()}>
                <button className="close-icon-btn" onClick={onCancel}>&times;</button>
                {/* <div className="modal-header">
                    <h3>{title}</h3>
                </div> */}
                <div className="modal-body">
                    {renderContent()}
                </div>
                {/* <div className="modal-footer">
                    <button className="modal-btn cancel-btn" onClick={onCancel}>
                        {cancelText}
                    </button>
                    <button className="modal-btn confirm-btn" onClick={onConfirm}>
                        {confirmText}
                    </button>
                </div> */}
            </div>
        </div>
    );
};

export default ExpandMsgModal;