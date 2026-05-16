import React from 'react';
import './PredictionMatrixModal.css';

const PredictionMatrixModal = ({ isOpen, onClose, data, fullSentence }) => {
    if (!isOpen || !data || data.length === 0) return null;

    // data structure expected:
    // [
    //   { word: "I", candidates: [ {word: "I", confidence: 0.9}, {word: "1", confidence: 0.6}, ... ] },
    //   ...
    // ]

    // We want rows to be Top 1, Top 2, Top 3
    // Columns to be the words in the sentence

    const rows = [0, 1, 2]; // For Top 1, 2, 3

    return (
        <div className="prediction-modal-overlay">
            <div className="prediction-modal-content">
                <div className="prediction-modal-header">
                    <h3>Prediction Analysis</h3>
                    <button className="prediction-modal-close" onClick={onClose}>&times;</button>
                </div>

                <div style={{ marginBottom: '15px', fontStyle: 'italic', color: '#555' }}>
                    <strong>Sentence:</strong> {fullSentence}
                </div>

                <div className="prediction-table-container">
                    <table className="prediction-table">
                        <thead>
                            <tr>
                                {data.map((item, index) => (
                                    <th key={index}>Word {index + 1}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((rowIndex) => (
                                <tr key={rowIndex}>
                                    {data.map((wordData, colIndex) => {
                                        const candidate = wordData.candidates && wordData.candidates[rowIndex];
                                        return (
                                            <td key={colIndex} className={rowIndex === 0 ? 'top-1' : ''}>
                                                {candidate ? (
                                                    <div className="prediction-cell">
                                                        <span className="prediction-word">{candidate.word}</span>
                                                        <span className="prediction-conf">({(candidate.confidence * 100).toFixed(0)}%)</span>
                                                    </div>
                                                ) : (
                                                    <span style={{ color: '#ccc' }}>-</span>
                                                )}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default PredictionMatrixModal;
