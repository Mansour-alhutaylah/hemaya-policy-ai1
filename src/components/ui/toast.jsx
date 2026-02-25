import * as React from "react";
import { X, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

// Viewport container — bottom-right corner
const ToastViewport = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[380px] max-w-[calc(100vw-2rem)]",
      className
    )}
    {...props}
  />
));
ToastViewport.displayName = "ToastViewport";

// Keep ToastProvider as a passthrough for compatibility
const ToastProvider = ({ children }) => <>{children}</>;

const Toast = React.forwardRef(
  ({ className, variant = "default", entering, exiting, progress, children, ...props }, ref) => {
    const isDestructive = variant === "destructive";

    return (
      <div
        ref={ref}
        className={cn(
          "toast-notification group pointer-events-auto relative w-full overflow-hidden",
          "rounded-xl border shadow-xl bg-white",
          "flex flex-col gap-0",
          isDestructive
            ? "border-l-4 border-l-red-500 border-red-100"
            : "border-l-4 border-l-emerald-500 border-slate-100",
          entering && "toast-enter",
          exiting && "toast-exit",
          !entering && !exiting && "toast-visible",
          className
        )}
        {...props}
      >
        {/* Content */}
        <div className="flex items-start gap-3 px-4 pt-4 pb-3">
          {/* Icon */}
          <div className={cn(
            "mt-0.5 shrink-0 rounded-full p-1",
            isDestructive ? "bg-red-100 text-red-600" : "bg-emerald-50 text-emerald-600"
          )}>
            {isDestructive
              ? <AlertCircle className="h-4 w-4" />
              : <CheckCircle2 className="h-4 w-4" />}
          </div>

          {/* Text */}
          <div className="flex-1 min-w-0">
            {children}
          </div>

          {/* Close button */}
          <button
            toast-close=""
            onClick={props.onClose}
            className="shrink-0 rounded-md p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus:outline-none"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Progress bar */}
        {typeof progress === "number" && (
          <div className="h-0.5 w-full bg-slate-100">
            <div
              className={cn(
                "h-full transition-none",
                isDestructive ? "bg-red-400" : "bg-emerald-500"
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>
    );
  }
);
Toast.displayName = "Toast";

const ToastTitle = React.forwardRef(({ className, ...props }, ref) => (
  <p ref={ref} className={cn("text-sm font-semibold text-slate-900 leading-tight", className)} {...props} />
));
ToastTitle.displayName = "ToastTitle";

const ToastDescription = React.forwardRef(({ className, ...props }, ref) => (
  <p ref={ref} className={cn("text-xs text-slate-500 mt-0.5 leading-relaxed", className)} {...props} />
));
ToastDescription.displayName = "ToastDescription";

const ToastClose = React.forwardRef(({ className, ...props }, ref) => (
  <button ref={ref} className={cn("hidden", className)} {...props} />
));
ToastClose.displayName = "ToastClose";

const ToastAction = React.forwardRef(({ className, ...props }, ref) => (
  <button
    ref={ref}
    className={cn("mt-1 text-xs font-medium text-emerald-600 hover:underline focus:outline-none", className)}
    {...props}
  />
));
ToastAction.displayName = "ToastAction";

export {
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
  ToastAction,
}; 