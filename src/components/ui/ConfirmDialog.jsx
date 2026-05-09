import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Trash2 } from 'lucide-react';

/**
 * Phase UI-2: shared destructive-action confirm dialog.
 *
 * Replaces ad-hoc window.confirm() prompts and avoids re-implementing
 * the same Dialog scaffold on every page that needs to confirm a
 * destructive action.
 *
 *   <ConfirmDialog
 *     open={!!target}
 *     onOpenChange={(o) => !o && setTarget(null)}
 *     title="Delete report?"
 *     description='This will permanently remove the file. This cannot be undone.'
 *     confirmLabel="Delete report"
 *     onConfirm={() => { mutate(target.id); setTarget(null); }}
 *     pending={mutation.isPending}
 *   />
 *
 * Defaults to a destructive (red) confirm button. Pass tone="default"
 * for a non-destructive confirmation.
 */
export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  pending = false,
  tone = 'destructive', // 'destructive' | 'default'
  icon,
}) {
  const isDestructive = tone === 'destructive';
  const Icon = icon || (isDestructive ? Trash2 : AlertTriangle);

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange?.(o)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle
            className={
              isDestructive
                ? 'flex items-center gap-2 text-red-600 dark:text-red-400'
                : 'flex items-center gap-2'
            }
          >
            <Icon className="w-5 h-5" />
            {title}
          </DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <div className="flex justify-end gap-2 mt-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange?.(false)}
            disabled={pending}
          >
            {cancelLabel}
          </Button>
          <Button
            onClick={onConfirm}
            disabled={pending}
            className={
              isDestructive
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-emerald-600 hover:bg-emerald-700'
            }
          >
            {isDestructive ? <Trash2 className="w-4 h-4 mr-1.5" /> : null}
            {pending ? 'Working…' : confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
