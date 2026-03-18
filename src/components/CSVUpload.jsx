// MIT License - Copyright (c) 2024 Finance App

import { useState, useCallback } from 'react';

export default function CSVUpload({ onUpload }) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const handleFile = useCallback((file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a .csv file.');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        onUpload(e.target.result);
        setError('');
      } catch (err) {
        setError(err.message);
      }
    };
    reader.readAsText(file);
  }, [onUpload]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files[0]);
  }, [handleFile]);

  const onDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  return (
    <div className="upload-page">
      <div className="upload-hero">
        <h1 className="upload-hero-title">Personal Finance Dashboard</h1>
        <p className="upload-hero-sub">Upload your SoFi CSV export to get started</p>
      </div>

      <div
        className={`upload-zone ${dragging ? 'dragging' : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={() => setDragging(false)}
      >
        <div className="upload-icon-wrap">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <p className="upload-title">Drag and drop your CSV here</p>
        <p className="upload-or">or</p>
        <label className="upload-btn">
          Browse File
          <input
            type="file"
            accept=".csv"
            hidden
            onChange={e => handleFile(e.target.files[0])}
          />
        </label>
        <p className="upload-hint">SoFi checking and savings CSV exports are supported</p>
      </div>

      {error && <p className="upload-error">{error}</p>}

      <div className="upload-steps">
        <div className="step">
          <span className="step-num">1</span>
          <span className="step-text">Log in to SoFi and go to your account</span>
        </div>
        <div className="step">
          <span className="step-num">2</span>
          <span className="step-text">Click "Download transactions" and export as CSV</span>
        </div>
        <div className="step">
          <span className="step-num">3</span>
          <span className="step-text">Drop the file above and explore your data</span>
        </div>
      </div>
    </div>
  );
}
