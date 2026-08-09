import { useActionState, useOptimistic, useFormStatus, useState } from 'react';

// -----------------------------------------------------------------------------
// 1. Interfaces & Types
// -----------------------------------------------------------------------------
export interface Task {
  id: string;
  title: string;
  isCompleted: boolean;
}

export interface TaskManagerProps {
  initialTasks: Task[];
  onTaskCreate: (title: string) => Promise<Task>;
  onTaskToggle?: (taskId: string, isCompleted: boolean) => void;
}

interface ActionState {
  error: string | null;
  successMessage: string | null;
}

// -----------------------------------------------------------------------------
// 2. Sub-components (Sub-feature primitives)
// -----------------------------------------------------------------------------
function SubmitButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="px-4 py-2 bg-indigo-600 text-white rounded-md font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
    >
      {pending ? 'Adding Task...' : 'Add Task'}
    </button>
  );
}

// -----------------------------------------------------------------------------
// 3. Main Feature Component
// -----------------------------------------------------------------------------
export function TaskManager({
  initialTasks,
  onTaskCreate,
  onTaskToggle,
}: TaskManagerProps) {
  const [filterQuery, setFilterQuery] = useState('');

  // Form action state management via React 19 useActionState
  const [actionState, formAction] = useActionState<ActionState, FormData>(
    async (_prevState, formData) => {
      const title = formData.get('taskTitle') as string;
      if (!title || title.trim() === '') {
        return { error: 'Task title cannot be empty', successMessage: null };
      }

      try {
        await onTaskCreate(title);
        return { error: null, successMessage: 'Task added successfully!' };
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to add task';
        return { error: message, successMessage: null };
      }
    },
    { error: null, successMessage: null }
  );

  // Optimistic UI updates
  const [optimisticTasks, addOptimisticTask] = useOptimistic(
    initialTasks,
    (currentTasks, newTitle: string) => [
      ...currentTasks,
      {
        id: `temp-${Date.now()}`,
        title: newTitle,
        isCompleted: false,
      },
    ]
  );

  // Internal event handlers following handle[Event] naming
  const handleFilterChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilterQuery(event.target.value);
  };

  const handleTaskToggle = (taskId: string, currentStatus: boolean) => {
    onTaskToggle?.(taskId, !currentStatus);
  };

  const filteredTasks = optimisticTasks.filter((task) =>
    task.title.toLowerCase().includes(filterQuery.toLowerCase())
  );

  return (
    <div className="max-w-xl mx-auto p-6 bg-white rounded-xl shadow-md border border-slate-100">
      <h2 className="text-2xl font-bold text-slate-900 mb-4">Task Manager</h2>

      {/* Task Creation Form */}
      <form
        action={async (formData) => {
          const title = formData.get('taskTitle') as string;
          if (title?.trim()) {
            addOptimisticTask(title);
          }
          await formAction(formData);
        }}
        className="flex gap-2 mb-6"
      >
        <input
          name="taskTitle"
          type="text"
          placeholder="What needs to be done?"
          className="flex-1 px-4 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <SubmitButton />
      </form>

      {/* Action Messages */}
      {actionState.error && (
        <p className="mb-4 text-sm text-red-600 bg-red-50 p-3 rounded-md">{actionState.error}</p>
      )}
      {actionState.successMessage && (
        <p className="mb-4 text-sm text-emerald-600 bg-emerald-50 p-3 rounded-md">
          {actionState.successMessage}
        </p>
      )}

      {/* Filter Input */}
      <div className="mb-4">
        <input
          type="text"
          value={filterQuery}
          onChange={handleFilterChange}
          placeholder="Filter tasks..."
          className="w-full px-3 py-1.5 text-sm border border-slate-200 rounded-md focus:outline-none focus:border-slate-400"
        />
      </div>

      {/* Task List */}
      <ul className="divide-y divide-slate-100">
        {filteredTasks.length === 0 ? (
          <li className="py-4 text-center text-slate-400 text-sm">No tasks found</li>
        ) : (
          filteredTasks.map((task) => (
            <li key={task.id} className="py-3 flex items-center justify-between">
              <span
                className={`text-sm ${
                  task.isCompleted ? 'line-through text-slate-400' : 'text-slate-700'
                }`}
              >
                {task.title}
              </span>
              <button
                type="button"
                onClick={() => handleTaskToggle(task.id, task.isCompleted)}
                className="text-xs px-2.5 py-1 rounded bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors"
              >
                {task.isCompleted ? 'Mark Pending' : 'Complete'}
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
