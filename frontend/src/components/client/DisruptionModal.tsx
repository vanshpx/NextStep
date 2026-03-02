"use client";

import { X, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import { summarizeIssue } from "@/lib/ai";

interface DisruptionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (type: string, details?: string) => void;
    activityTitle: string;
}

export default function DisruptionModal({ isOpen, onClose, onSubmit, activityTitle }: DisruptionModalProps) {
    const [selectedType, setSelectedType] = useState('Delay');
    const [description, setDescription] = useState('');
    const [summary, setSummary] = useState('');
    const [isSummarizing, setIsSummarizing] = useState(false);

    useEffect(() => {
        if (!isOpen) return;

        const timeoutId = setTimeout(async () => {
            if (description.trim().length > 5) {
                setIsSummarizing(true);
                try {
                    const res = await summarizeIssue(selectedType, description);
                    setSummary(res);
                } catch (err) {
                    console.error("Summarization failed", err);
                } finally {
                    setIsSummarizing(false);
                }
            } else {
                setSummary(selectedType);
            }
        }, 800);

        return () => clearTimeout(timeoutId);
    }, [description, selectedType, isOpen]);

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        className="bg-white border border-gray-200 w-full max-w-md rounded-xl shadow-2xl overflow-hidden"
                    >
                        <div className="p-6 border-b border-gray-100 flex justify-between items-center">
                            <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                <AlertTriangle className="w-5 h-5 text-red-600" />
                                Report Issue
                            </h3>
                            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="p-6 space-y-4">
                            <div className="bg-red-50 p-3 rounded-lg border border-red-100">
                                <p className="text-sm font-medium text-red-800">
                                    Reporting issue for: <span className="font-bold">{activityTitle}</span>
                                </p>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-700">Issue Type</label>
                                <select
                                    value={selectedType}
                                    onChange={(e) => setSelectedType(e.target.value)}
                                    className="w-full h-10 px-3 rounded-md bg-white border border-gray-300 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                                >
                                    <option>Delay</option>
                                    <option>Want to skip</option>
                                    <option>Do it later</option>
                                    <option>Bad weather</option>
                                    <option>Fatigue</option>
                                    <option>Flight missed</option>
                                    <option>Other</option>
                                </select>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-700">Description</label>
                                <textarea
                                    value={description}
                                    onChange={(e) => setDescription(e.target.value)}
                                    className="w-full h-24 p-3 rounded-md bg-white border border-gray-300 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent resize-none"
                                    placeholder="e.g. Flight is delayed by 2 hours because of air traffic at JFK..."
                                />
                            </div>

                            <div className="flex gap-3 pt-4">
                                <Button variant="outline" onClick={onClose} className="flex-1 hover:bg-gray-50 text-gray-700 border-gray-300">
                                    Cancel
                                </Button>
                                <Button
                                    onClick={() => {
                                        onSubmit(summary || selectedType, description);
                                        onClose();
                                    }}
                                    className="flex-1 bg-primary-600 hover:bg-primary-700 text-white"
                                >
                                    Submit Report
                                </Button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}
