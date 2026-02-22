"use client";

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
    "inline-flex items-center justify-center whitespace-nowrap text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
    {
        variants: {
            variant: {
                default: "text-white",
                secondary: "bg-white text-gray-700 border border-[#e5e7eb] hover:bg-[#f8fafc] transition-colors",
                outline: "border border-[#e5e7eb] bg-transparent hover:bg-[#f8fafc] text-gray-700",
                ghost: "hover:bg-[#f8fafc] text-gray-600 hover:text-gray-900",
                link: "text-[#2563eb] underline-offset-4 hover:underline",
            },
            size: {
                default: "px-[14px] py-[9px] rounded-[6px]",
                sm: "px-3 py-1.5 rounded-[4px] text-xs",
                lg: "px-5 py-3 rounded-[8px] text-base",
                icon: "h-8 w-8 rounded-[6px]",
            },
        },
        defaultVariants: {
            variant: "default",
            size: "default",
        },
    }
)

// Inject the brand color as a style since it needs to be dynamic
const variantStyles: Record<string, React.CSSProperties> = {
    default: { backgroundColor: "var(--brand)" },
};

export interface ButtonProps
    extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant, size, style, onMouseEnter, onMouseLeave, ...props }, ref) => {
        const [hovered, setHovered] = React.useState(false);
        const v = variant ?? "default";

        const baseStyle = variantStyles[v] ?? {};
        const hoverStyle = v === "default" && hovered ? { backgroundColor: "var(--brand-hover)" } : {};

        return (
            <button
                className={cn(buttonVariants({ variant, size, className }))}
                ref={ref}
                style={{ ...baseStyle, ...hoverStyle, ...style }}
                onMouseEnter={(e) => { setHovered(true); onMouseEnter?.(e); }}
                onMouseLeave={(e) => { setHovered(false); onMouseLeave?.(e); }}
                {...props}
            />
        )
    }
)
Button.displayName = "Button"

export { Button, buttonVariants }
