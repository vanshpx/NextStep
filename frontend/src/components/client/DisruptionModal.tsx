"use client";

import { X, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { motion, AnimatePresence } from "framer-motion";

interface DisruptionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (type: string, details?: string) => void;
    activityTitle: string;
}

export default function DisruptionModal({ isOpen, onClose, onSubmit, activityTitle }: DisruptionModalProps) {
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
                                <select className="w-full h-10 px-3 rounded-md bg-white border border-gray-300 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                                    <option>Delay</option>
                                    <option>Cancellation</option>
                                    <option>Missed Connection</option>
                                    <option>Lost Item</option>
                                    <option>Other</option>
                                </select>
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-700">Description</label>
                                <textarea
                                    className="w-full h-24 p-3 rounded-md bg-white border border-gray-300 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent resize-none"
                                    placeholder="Please maintain details about the incident..."
                                />
                            </div>

                            <div className="flex gap-3 pt-4">
                                <Button variant="outline" onClick={onClose} className="flex-1 hover:bg-gray-50 text-gray-700 border-gray-300">
                                    Cancel
                                </Button>
                                <Button
                                    onClick={() => {
                                        onSubmit('Expected Delay', 'Traffic'); // Example values, actual implementation would get these from state
                                        onClose();
                                    }}
                                    className="flex-1 bg-red-600 hover:bg-red-700 text-white shadow-md shadow-red-200"
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
