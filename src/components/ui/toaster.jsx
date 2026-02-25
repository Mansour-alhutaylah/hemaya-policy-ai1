import { useState, useEffect, useRef } from "react";
import { useToast } from "@/components/ui/use-toast";
import {
  Toast,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "@/components/ui/toast";

const AUTO_DISMISS_MS = 4000;
const EXIT_DURATION_MS = 350;

function AnimatedToast({ id, title, description, action, variant, open, onDismiss }) {
  const [phase, setPhase] = useState("entering"); // entering | visible | exiting
  const [progress, setProgress] = useState(100);
  const startRef = useRef(null);
  const rafRef = useRef(null);
  const exitTimerRef = useRef(null);

  const startProgress = () => {
    startRef.current = performance.now();
    const tick = (now) => {
      const elapsed = now - startRef.current;
      const pct = Math.max(0, 100 - (elapsed / AUTO_DISMISS_MS) * 100);
      setProgress(pct);
      if (elapsed < AUTO_DISMISS_MS) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    rafRef.current = requestAnimationFrame(tick);
  };

  useEffect(() => {
    const t = setTimeout(() => {
      setPhase("visible");
      startProgress();
    }, 20);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!open && phase !== "exiting") {
      triggerExit();
    }
  }, [open]);

  const triggerExit = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    setPhase("exiting");
    setProgress(0);
    exitTimerRef.current = setTimeout(() => onDismiss(id), EXIT_DURATION_MS);
  };

  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
  }, []);

  return (
    <Toast
      variant={variant}
      entering={phase === "entering"}
      exiting={phase === "exiting"}
      progress={progress}
      onClose={triggerExit}
    >
      {title && <ToastTitle>{title}</ToastTitle>}
      {description && <ToastDescription>{description}</ToastDescription>}
      {action}
    </Toast>
  );
}

export function Toaster() {
  const { toasts, dismiss } = useToast();
  const [rendered, setRendered] = useState([]);

  useEffect(() => {
    setRendered(prev => {
      const existingIds = new Set(prev.map(t => t.id));
      const newOnes = toasts.filter(t => !existingIds.has(t.id));
      const updated = prev.map(p => ({ ...p, ...toasts.find(t => t.id === p.id) }));
      return [...updated, ...newOnes];
    });
  }, [toasts]);

  const handleDismiss = (id) => {
    dismiss(id);
    setRendered(prev => prev.filter(t => t.id !== id));
  };

  return (
    <ToastProvider>
      <ToastViewport>
        {rendered.map(({ id, title, description, action, variant, open }) => (
          <AnimatedToast
            key={id}
            id={id}
            title={title}
            description={description}
            action={action}
            variant={variant}
            open={open}
            onDismiss={handleDismiss}
          />
        ))}
      </ToastViewport>
    </ToastProvider>
  );
} 